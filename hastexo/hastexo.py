import time
import logging
import textwrap

from xblock.core import XBlock, XML_NAMESPACES
from xblock.fields import Scope, Float, String, Dict, List, Integer
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xblockutils.settings import XBlockWithSettingsMixin

from django.db import transaction
from django.utils import timezone
from lxml import etree

from .models import Stack
from .utils import (UP_STATES, LAUNCH_STATE, LAUNCH_ERROR_STATE, SETTINGS_KEY,
                    get_xblock_settings, get_stack, update_stack,
                    update_stack_fields)
from .tasks import LaunchStackTask, CheckStudentProgressTask

logger = logging.getLogger(__name__)
loader = ResourceLoader(__name__)


class LaunchError(Exception):
    error_msg = ""

    def __init__(self, error_msg):
        super(LaunchError, self).__init__()

        self.error_msg = error_msg


@XBlock.wants('settings')
class HastexoXBlock(XBlock,
                    XBlockWithSettingsMixin,
                    StudioEditableXBlockMixin):
    """
    Provides lab environments and an SSH connection to them.

    """
    # Settings with defaults.
    display_name = String(
        default="Lab",
        scope=Scope.settings,
        help="Title to display")
    weight = Float(
        default=1,
        scope=Scope.settings,
        help="Defines the maximum total grade of the block.")

    # Mandatory: must be set per instance.
    stack_template_path = String(
        scope=Scope.settings,
        help="The relative path to the uploaded orchestration template. "
             "For example, \"hot_lab.yaml\".")
    stack_user_name = String(
        scope=Scope.settings,
        help="The name of the training user in the stack.")
    stack_protocol = String(
        values=["ssh", "rdp", "vnc"],
        default="ssh",
        scope=Scope.settings,
        help="What protocol to use for the connection. "
             "Currently, \"ssh\", \"rdp\", or \"vnc\".")

    # Optional
    launch_timeout = Integer(
        default=None,
        scope=Scope.settings,
        help="Timeout for a launch operation, in seconds.  Takes precedence"
             "over the globally defined timeout.")

    # Set via XML
    ports = List(
        default=[],
        scope=Scope.settings,
        enforce_type=True,
        xml_node=True,
        help="What ports are available in the stack.")
    providers = List(
        default=[],
        scope=Scope.settings,
        enforce_type=True,
        xml_node=True,
        help="List of providers to launch the stack in.")
    tests = List(
        default=[],
        scope=Scope.content,
        enforce_type=True,
        xml_node=True,
        help="The list of tests to run.")

    # Deprecated in favor or "providers"
    provider = String(
        default="",
        scope=Scope.settings,
        help="Where to launch the stack. (DEPRECATED)")

    # User state, per instance.
    stack_run = String(
        default="",
        scope=Scope.user_state,
        help="The name of the run")
    stack_name = String(
        default="",
        scope=Scope.user_state,
        help="The name of the user's stack")
    stack_provider = String(
        default="",
        scope=Scope.user_state,
        help="The provider selected for the current launch of the stack")
    check_id = String(
        default="",
        scope=Scope.user_state,
        help="The check task id")
    check_timestamp = Integer(
        default=None,
        scope=Scope.user_state,
        help="When the check task was launched")
    check_status = Dict(
        default=None,
        scope=Scope.user_state,
        help="The check status")

    editable_fields = (
        'display_name',
        'weight',
        'stack_template_path',
        'stack_user_name',
        'stack_protocol',
        'launch_timeout',
        'ports',
        'providers',
        'tests')

    has_author_view = True
    has_score = True
    has_children = True
    icon_class = 'problem'
    block_settings_key = SETTINGS_KEY

    @classmethod
    def parse_xml(cls, node, runtime, keys, id_generator):
        """
        DEPRECATED: the 'option' namespace is now the preferred way to specify
        tests, ports, and providers.  This custom parser will be removed in a
        future version.

        """
        block = runtime.construct_xblock_from_class(cls, keys)

        # Find children
        for child in node:
            if child.tag is etree.Comment:
                continue

            qname = etree.QName(child)
            tag = qname.localname
            namespace = qname.namespace

            if namespace == XML_NAMESPACES["option"]:
                cls._set_field_if_present(block, tag, child.text, child.attrib)
            elif tag == "test":
                text = child.text

                # Fix up whitespace.
                if text[0] == "\n":
                    text = text[1:]
                text.rstrip()
                text = textwrap.dedent(text)

                block.tests.append(text)
            elif tag == "port":
                name = child.attrib["name"]
                if not name:
                    raise KeyError("name")
                number = child.attrib["number"]
                if not number:
                    raise KeyError("number")
                number = int(number)
                port = {"name": name,
                        "number": number}
                block.ports.append(port)
            elif tag == "provider":
                name = child.attrib["name"]
                if not name:
                    raise KeyError("name")
                capacity = child.attrib.get("capacity")
                if capacity in (None, "None"):
                    capacity = -1
                else:
                    # This will raise a TypeError if the string literal
                    # cannot be converted
                    capacity = int(capacity)
                environment = child.attrib.get("environment", None)
                provider = {"name": name,
                            "capacity": capacity,
                            "environment": environment}

                block.providers.append(provider)
            else:
                block.runtime.add_node_as_child(block, child, id_generator)

        # Attributes become fields.
        for name, value in node.items():
            cls._set_field_if_present(block, name, value, {})

        return block

    def author_view(self, context=None):
        """ Studio View """
        msg = u"This XBlock only renders content when viewed via the LMS."
        return Fragment(u'<em>%s</em></p>' % msg)

    def is_correct(self):
        if not (self.check_status and isinstance(self.check_status, dict)):
            return False
        else:
            total = self.check_status.get('total')
            if not total:
                return False
            else:
                score = self.check_status.get('pass')
                return score == total

    def get_block_ids(self):
        try:
            course_id = getattr(self.xmodule_runtime, 'course_id', 'all')
            student_id = self.xmodule_runtime.anonymous_student_id
        except AttributeError:
            course_id = 'all'
            student_id = self.scope_ids.user_id

        return (course_id, student_id)

    def get_launch_timeout(self, settings):
        launch_timeout = None
        if self.launch_timeout:
            launch_timeout = self.launch_timeout
        else:
            launch_timeout = settings.get("launch_timeout")

        return launch_timeout

    def read_from_contentstore(self, path):
        """
        Loads a file directly from the course's content store.

        """
        if not path:
            return None

        course_id, _ = self.get_block_ids()
        contents = None
        try:
            from xmodule.contentstore.content import StaticContent
            from xmodule.contentstore.django import contentstore
            from xmodule.exceptions import NotFoundError

            loc = StaticContent.compute_location(course_id, path)
            asset = contentstore().find(loc)
            contents = asset.data
        except (ImportError, NotFoundError):
            pass

        return contents

    def student_view(self, context=None):
        """
        The primary view of the HastexoXBlock, shown to students when viewing
        courses.
        """
        def error_frag(msg):
            """ Build a fragment to display runtime errors. """
            context = {'error_msg': msg}
            html = loader.render_template('static/html/error.html', context)
            frag = Fragment(html)
            frag.add_css_url(
                self.runtime.local_resource_url(self,
                                                'public/css/main.css')
            )
            return frag

        # Load configuration
        settings = get_xblock_settings()

        # Get the course id and anonymous user id, and derive the stack name
        # from them
        course_id, anonymous_student_id = self.get_block_ids()
        self.stack_run = "%s_%s" % (course_id.course, course_id.run)
        self.stack_name = "%s_%s" % (self.stack_run, anonymous_student_id)

        # Render the HTML template
        html = loader.render_template('static/html/main.html')
        frag = Fragment(html)

        # Add the public CSS and JS
        frag.add_css_url(
            self.runtime.local_resource_url(self, 'public/css/main.css')
        )
        frag.add_javascript_url(
            self.runtime.local_resource_url(self, 'public/js/plugins.js')
        )
        frag.add_javascript_url(
            self.runtime.local_resource_url(self, 'public/js/main.js')
        )

        # Create the stack in the database
        with transaction.atomic():
            stack, _ = Stack.objects.select_for_update().get_or_create(
                student_id=anonymous_student_id,
                course_id=course_id,
                name=self.stack_name
            )

            # Set the port
            port = None
            if len(self.ports) > 0:
                ports = [p["number"] for p in self.ports]
                port = stack.port
                if not port or port not in ports:
                    port = self.ports[0]["number"]

            # Save
            stack.protocol = self.stack_protocol
            stack.port = port
            stack.save(update_fields=["protocol", "port"])

        # Call the JS initialization function
        frag.initialize_js('HastexoXBlock', {
            "terminal_url": settings.get("terminal_url"),
            "timeouts": settings.get("js_timeouts"),
            "has_tests": len(self.tests) > 0,
            "protocol": self.stack_protocol,
            "ports": self.ports,
            "port": port
        })

        return frag

    def update_stack(self, data):
        course_id, student_id = self.get_block_ids()
        update_stack(self.stack_name, course_id, student_id, data)

    def get_stack(self, prop=None):
        course_id, student_id = self.get_block_ids()
        return get_stack(self.stack_name, course_id, student_id, prop)

    def launch_stack_task(self, soft_time_limit, kwargs):
        task = LaunchStackTask()
        time_limit = soft_time_limit + 30
        result = task.apply_async(
            kwargs=kwargs,
            expires=soft_time_limit,
            soft_time_limit=soft_time_limit,
            time_limit=time_limit
        )

        return result

    def launch_stack_task_result(self, task_id):
        return LaunchStackTask().AsyncResult(task_id)

    def launch_stack(self, stack, settings, reset=False):
        stack_template = self.read_from_contentstore(self.stack_template_path)
        if stack_template is None:
            raise LaunchError("Stack template file not found.")

        providers = []
        if len(self.providers):
            for provider in self.providers:
                p = dict(provider)
                env_path = p.get("environment")
                p["environment"] = self.read_from_contentstore(env_path)
                if p["environment"] is None:
                    logger.info('Provider environment file for [%s]'
                                'not found.' % p["name"])

                providers.append(p)
        # For backward compatibility
        elif self.provider:
            providers.append({
                "name": self.provider,
                "capacity": -1,
                "environment": None
            })
        # No providers have been configured.  Use the "default" one if it
        # exists, or the first one if not.
        else:
            configured_providers = settings.get("providers", {})
            provider_name = None
            if configured_providers.get("default"):
                provider_name = "default"
            else:
                try:
                    provider_name = configured_providers.iterkeys().next()
                except StopIteration:
                    pass

            if provider_name:
                providers.append({
                    "name": provider_name,
                    "capacity": -1,
                    "environment": None
                })

        course_id, student_id = self.get_block_ids()
        kwargs = {
            "providers": providers,
            "protocol": self.stack_protocol,
            "port": stack.port,
            "stack_template": stack_template,
            "stack_run": self.stack_run,
            "stack_name": self.stack_name,
            "stack_user_name": self.stack_user_name,
            "course_id": str(course_id),
            "student_id": student_id,
            "reset": reset
        }
        launch_timeout = self.get_launch_timeout(settings)

        # Run
        result = self.launch_stack_task(launch_timeout, kwargs)

        # Update stack
        stack.status = LAUNCH_STATE
        stack.error_msg = ""
        stack.launch_task_id = result.id
        stack.launch_timestamp = timezone.now()

        logger.info('Fired async launch task [%s] for [%s]' % (
            result.id, self.stack_name))

        return result

    def process_stack_result(self, stack, result):
        if result and result.ready():
            # Clear launch task ID from the database
            stack.launch_task_id = ""

            if (result.successful() and
                    isinstance(result.result, dict) and not
                    result.result.get('error')):
                data = result.result

                # Sync current provider
                self.stack_provider = data.get("provider", "")

                # Save status to the database
                update_stack_fields(stack, data)
            else:
                raise LaunchError(repr(result.result))

        else:
            data = {"status": LAUNCH_STATE}

        return data

    def process_stack_data(self, stack):
        data = {
            "status": stack.status,
            "error_msg": stack.error_msg,
            "ip": stack.ip,
            "user": stack.user,
            "key": stack.key,
            "password": stack.password
        }

        return data

    def process_stack_error(self, stack, error_msg):
        data = {
            "status": LAUNCH_ERROR_STATE,
            "error_msg": error_msg
        }

        # Save status
        update_stack_fields(stack, data)

        return data

    def get_user_stack_status_atomic(self, stack, request_data):
        settings = get_xblock_settings()
        initialize = request_data.get("initialize", False)
        reset = request_data.get("reset", False)

        # Calculate the time since the suspend timer was last reset.
        suspend_timeout = settings.get("suspend_timeout")
        suspend_timestamp = stack.suspend_timestamp
        time_since_suspend = 0
        if suspend_timeout and suspend_timestamp:
            time_since_suspend = (timezone.now() - suspend_timestamp).seconds

        # Get the last stack status
        prev_status = stack.status

        # No last stack status: this is the first time
        # the user launches this stack.
        if not prev_status:
            logger.info('Launching stack [%s] '
                        'for the first time.' % (self.stack_name))
            try:
                result = self.launch_stack(stack, settings, reset)
                stack_data = self.process_stack_result(stack, result)
            except LaunchError as e:
                stack_data = self.process_stack_error(stack, e.error_msg)

        # There was a previous attempt at launching the stack
        elif prev_status == LAUNCH_STATE:
            # Update task result
            launch_task_id = stack.launch_task_id
            result = self.launch_stack_task_result(launch_task_id)
            try:
                stack_data = self.process_stack_result(stack, result)
            except LaunchError as e:
                stack_data = self.process_stack_error(stack, e.error_msg)

            current_status = stack_data.get("status")

            # Stack is still LAUNCH_STATE since last check.
            if current_status == LAUNCH_STATE:
                # Calculate time since launch
                time_since_launch = 0
                launch_timestamp = stack.launch_timestamp
                if launch_timestamp:
                    time_since_launch = (timezone.now() -
                                         launch_timestamp).seconds
                launch_timeout = self.get_launch_timeout(settings)

                # Check if the pending task hasn't timed out.
                if time_since_launch <= launch_timeout:
                    # The pending task still has some time to finish.
                    # Please wait.
                    logger.info('Launch pending for [%s]' % (self.stack_name))

                elif initialize or reset:
                    # Timeout reached, but the user just entered the page or
                    # requested a reset.  Try launching the stack again.
                    if initialize:
                        logger.info('Launch timeout detected on initialize. '
                                    'Launching stack [%s]' % (self.stack_name))
                    else:
                        logger.info('Launch timeout detected on reset. '
                                    'Resetting stack [%s]' % (self.stack_name))
                    try:
                        result = self.launch_stack(stack, settings, reset)
                        stack_data = self.process_stack_result(stack, result)
                    except LaunchError as e:
                        stack_data = self.process_stack_error(stack,
                                                              e.error_msg)
                else:
                    # Timeout reached.  Consider the task a failure and let the
                    # user retry manually.
                    logger.error('Launch timeout reached for [%s] '
                                 'after %s seconds' % (self.stack_name,
                                                       time_since_launch))
                    error_msg = "Timeout when launching or resuming stack."
                    stack_data = self.process_stack_error(stack, error_msg)

            # Stack changed from LAUNCH_STATE to COMPLETE.
            elif current_status in UP_STATES:
                if reset or (suspend_timeout and time_since_suspend >= suspend_timeout):  # noqa: E501
                    if reset:
                        logger.info('Resetting successfully launched '
                                    'stack [%s].' % (self.stack_name))
                    else:
                        logger.info('Stack [%s] may have suspended. '
                                    'Relaunching.' % (self.stack_name))
                    try:
                        result = self.launch_stack(stack, settings, reset)
                        stack_data = self.process_stack_result(stack, result)
                    except LaunchError as e:
                        stack_data = self.process_stack_error(stack,
                                                              e.error_msg)

                # The stack couldn't have been suspended, yet.
                else:
                    logger.info('Successful launch detected for [%s], '
                                'with status [%s]' % (self.stack_name,
                                                      current_status))

            # Detected a failed launch attempt, but the user has requested a
            # retry, just entered the page, or requested a reset, so start from
            # scratch.
            elif initialize or reset:
                if reset:
                    logger.info('Resetting failed '
                                'stack [%s].' % (self.stack_name))
                else:
                    logger.info('Retrying previously failed '
                                'stack [%s].' % (self.stack_name))
                try:
                    result = self.launch_stack(stack, settings, reset)
                    stack_data = self.process_stack_result(stack, result)
                except LaunchError as e:
                    stack_data = self.process_stack_error(stack, e.error_msg)

            # Detected a failed launch attempt.
            # Report the error and let the user retry manually.
            else:
                logger.error('Failed launch detected for [%s], '
                             'with status [%s]' % (self.stack_name,
                                                   current_status))

        # The stack was previously launched successfully
        elif prev_status in UP_STATES:
            if reset or (suspend_timeout and time_since_suspend >= suspend_timeout):  # noqa: E501
                if reset:
                    logger.info('Resetting successfully launched '
                                'stack [%s].' % (self.stack_name))
                else:
                    logger.info('Stack [%s] may have suspended. '
                                'Relaunching.' % (self.stack_name))
                try:
                    result = self.launch_stack(stack, settings, reset)
                    stack_data = self.process_stack_result(stack, result)
                except LaunchError as e:
                    stack_data = self.process_stack_error(stack, e.error_msg)

            else:
                logger.info('Successful launch detected for [%s], '
                            'with status [%s]' % (self.stack_name,
                                                  prev_status))
                stack_data = self.process_stack_data(stack)

        # Detected a failed launch attempt, but the user just entered the page,
        # or requested a retry or reset, so start from scratch.
        elif initialize or reset:
            if reset:
                logger.info('Resetting failed stack [%s].' % (self.stack_name))
            else:
                logger.info('Retrying previously failed '
                            'stack [%s].' % (self.stack_name))
            try:
                result = self.launch_stack(stack, settings, reset)
                stack_data = self.process_stack_result(stack, result)
            except LaunchError as e:
                stack_data = self.process_stack_error(e.error_msg)

        # Detected a failed launch attempt.  Report the error and let the user
        # retry manually.
        else:
            logger.error('Failed launch detected for [%s], '
                         'with status [%s]' % (self.stack_name,
                                               prev_status))
            stack_data = self.process_stack_data(stack)

        # Reset the dead man's switch
        stack.suspend_timestamp = timezone.now()

        return stack_data

    @XBlock.json_handler
    def get_user_stack_status(self, request_data, suffix=''):
        course_id, student_id = self.get_block_ids()

        with transaction.atomic():
            stack, _ = Stack.objects.select_for_update().get_or_create(
                student_id=student_id,
                course_id=course_id,
                name=self.stack_name
            )
            stack_data = self.get_user_stack_status_atomic(stack, request_data)
            stack.save()

        return stack_data

    @XBlock.json_handler
    def keepalive(self, data, suffix=''):
        # Reset the dead man's switch
        self.update_stack({"suspend_timestamp": timezone.now()})

    def check_progress_task(self, soft_time_limit, **kwargs):
        task = CheckStudentProgressTask()
        time_limit = soft_time_limit + 30
        result = task.apply_async(
            kwargs=kwargs,
            expires=soft_time_limit,
            soft_time_limit=soft_time_limit,
            time_limit=time_limit
        )

        return result

    def check_progress_task_result(self, check_id):
        return CheckStudentProgressTask().AsyncResult(check_id)

    @XBlock.json_handler
    def get_check_status(self, data, suffix=''):
        """
        Checks the current student score.
        """
        settings = get_xblock_settings()
        check_timeout = settings.get("check_timeout")

        def _launch_check():
            stack = self.get_stack()
            logger.info('Executing tests for stack [%s], IP [%s], user [%s]:' %
                        (self.stack_name, stack.ip,
                         self.stack_user_name))
            for test in self.tests:
                logger.info('Test: %s' % test)

            kwargs = {
                "tests": self.tests,
                "stack_ip": stack.ip,
                "stack_user_name": self.stack_user_name,
                "stack_key": stack.key
            }
            result = self.check_progress_task(check_timeout, **kwargs)

            # Save task ID and timestamp
            self.check_id = result.id
            self.check_timestamp = int(time.time())

            return result

        def _process_result(result):
            if result.ready():
                # Clear the task ID so we know there is no task running.
                self.check_id = ""

                if (result.successful() and
                        isinstance(result.result, dict) and not
                        result.result.get('error')):
                    status = result.result

                    # Publish the grade
                    self.runtime.publish(self, 'grade', {
                        'value': status['pass'],
                        'max_value': status['total']
                    })
                else:
                    status = {
                        'status': 'ERROR',
                        'error_msg': 'Unexpected result: %s' % repr(result.result)  # noqa: E501
                    }
            else:
                status = {'status': 'CHECK_PROGRESS_PENDING'}

            # Store the result
            self.check_status = status

            return status

        # If a check task is running, return its status.
        if self.check_id:
            logger.info('Check progress task is running: %s' % self.check_id)
            result = self.check_progress_task_result(self.check_id)
            status = _process_result(result)

            if status['status'] == 'CHECK_PROGRESS_PENDING':
                time_since_check = int(time.time()) - self.check_timestamp

                # Check if the pending task hasn't timed out.
                if time_since_check >= check_timeout:
                    # Timeout reached.  Consider the task a failure and let the
                    # user retry manually.
                    logger.error('Check timeout reached for [%s] '
                                 'after %s seconds' % (self.stack_name,
                                                       time_since_check))
                    self.check_id = ""
                    status = {'status': 'ERROR',
                              'error_msg': "Timeout when checking progress."}

        # Otherwise, launch the check task.
        else:
            result = _launch_check()
            status = _process_result(result)

        return status

    @XBlock.json_handler
    def set_port(self, data, suffix=''):
        # Set the preferred stack port
        self.update_stack({"port": int(data.get("port"))})

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("HastexoXBlock",
             """<vertical_demo>
                <hastexo/>
                </vertical_demo>
             """),
        ]
