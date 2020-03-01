import time
import logging
import textwrap

from xblock.core import XBlock, XML_NAMESPACES
from xblock.fields import Scope, Float, String, Dict, List, Integer
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import (
    NestedXBlockSpec,
    StudioContainerWithNestedXBlocksMixin,
    StudioEditableXBlockMixin,
)
from xblockutils.settings import XBlockWithSettingsMixin

from django.db import transaction
from django.utils import timezone
from lxml import etree

from .models import Stack
from .common import (
    UP_STATES,
    DOWN_STATES,
    PENDING_STATES,
    LAUNCH_PENDING,
    LAUNCH_ERROR,
    SETTINGS_KEY,
    get_xblock_settings,
    get_stack,
    update_stack
)
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
                    StudioEditableXBlockMixin,
                    StudioContainerWithNestedXBlocksMixin):
    """
    Provides lab environments and an SSH connection to them.

    """
    CATEGORY = "hastexo"
    STUDIO_LABEL = "hastexo XBlock"

    # Settings with defaults.
    display_name = String(
        default="hastexo XBlock",
        scope=Scope.settings,
        help="Title to display")
    weight = Float(
        default=1,
        scope=Scope.settings,
        help="Defines the maximum total grade of the block.")

    # Mandatory: must be set per instance.
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
    stack_template_path = String(
        scope=Scope.settings,
        help="The relative path to the uploaded orchestration template. "
             "For example, \"hot_lab.yaml\".")
    launch_timeout = Integer(
        default=None,
        scope=Scope.settings,
        help="Timeout for a launch operation, in seconds.  Takes precedence"
             "over the globally defined timeout.")
    hook_script = String(
        scope=Scope.settings,
        help="The relative path to an uploaded executable script. "
             "For example, \"hot_script.sh\".")

    # Set via XML
    hook_events = Dict(
        default=None,
        scope=Scope.settings,
        enforce_type=True,
        xml_node=True,
        help="A dictionary of (string, boolean) pairs, where `string` is any "
             "of \"suspend\", \"resume\", and \"delete\".")
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

    # Deprecated in favor of "providers"
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
        'hook_script',
        'hook_events',
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
                template = child.attrib.get("template", None)
                environment = child.attrib.get("environment", None)
                provider = {"name": name,
                            "capacity": capacity,
                            "template": template,
                            "environment": environment}

                block.providers.append(provider)
            else:
                block.runtime.add_node_as_child(block, child, id_generator)

        # Attributes become fields.
        for name, value in node.items():
            cls._set_field_if_present(block, name, value, {})

        return block

    @property
    def allowed_nested_blocks(self):
        """
        Returns a list of allowed nested blocks.

        """
        additional_blocks = []
        try:
            from xmodule.video_module.video_module import VideoDescriptor
            _spec = NestedXBlockSpec(
                VideoDescriptor, category="video", label=u"Video"
            )
            additional_blocks.append(_spec)
        except ImportError:
            logger.warning("Unable to import VideoDescriptor", exc_info=True)

        try:
            from pdf import pdfXBlock
            _spec = NestedXBlockSpec(pdfXBlock, category="pdf", label=u"PDF")
            additional_blocks.append(_spec)
        except ImportError:
            logger.info("Unable to import pdfXblock", exc_info=True)

        return [
            NestedXBlockSpec(None, category="html", label=u"HTML")
        ] + additional_blocks

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

    def student_view(self, context=None):
        """
        The primary view of the HastexoXBlock, shown to students when viewing
        courses.
        """
        # Load configuration
        settings = get_xblock_settings()

        # Get the course id and anonymous user id, and derive the stack name
        # from them
        course_id, student_id = self.get_block_ids()
        self.stack_run = "%s_%s" % (course_id.course, course_id.run)
        self.stack_name = "%s_%s" % (self.stack_run, student_id)

        frag = Fragment()

        # Render children
        child_content = ""
        for child_id in self.children:
            child = self.runtime.get_block(child_id)
            child_fragment = child.render("student_view", context)
            frag.add_frag_resources(child_fragment)
            child_content += child_fragment.content

        # Render the main template
        frag.add_content(loader.render_django_template(
            "static/html/main.html", {"child_content": child_content}
        ))

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
        stack = self.create_stack(settings, course_id, student_id)

        # Call the JS initialization function
        frag.initialize_js('HastexoXBlock', {
            "terminal_url": settings.get("terminal_url"),
            "timeouts": settings.get("js_timeouts"),
            "has_tests": len(self.tests) > 0,
            "protocol": self.stack_protocol,
            "ports": self.ports,
            "port": stack.port
        })

        return frag

    @transaction.atomic
    def create_stack(self, settings, course_id, student_id):
        stack, _ = Stack.objects.select_for_update().get_or_create(
            student_id=student_id,
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

        # Set the providers
        providers = []
        if len(self.providers):
            for provider in self.providers:
                p = dict(provider)

                if not p.get("template"):
                    p["template"] = self.stack_template_path

                if not p["template"]:
                    raise Exception("Provider [%s] template file not "
                                    "provided for [%s]." %
                                    (p["name"], self.stack_name))
                providers.append(p)
        elif self.provider:
            # For backward compatibility
            if not self.stack_template_path:
                raise Exception("Provider [%s] template file not provided "
                                "for [%s]." % (self.provider,
                                               self.stack_name))

            providers.append({
                "name": self.provider,
                "capacity": -1,
                "template": self.stack_template_path,
                "environment": None
            })
        else:
            # No providers have been configured.  Use the "default" one if
            # it exists, or the first one if not.
            configured_providers = settings.get("providers", {})
            provider_name = None
            if configured_providers.get("default"):
                provider_name = "default"
            else:
                try:
                    provider_name = next(iter(configured_providers))
                except StopIteration:
                    pass

            if not provider_name:
                raise Exception("Provider not configured for [%s]." %
                                self.stack_name)
            elif not self.stack_template_path:
                raise Exception("Provider [%s] template file not "
                                "provided for [%s]." % (provider_name,
                                                        self.stack_name))
            else:
                providers.append({
                    "name": provider_name,
                    "capacity": -1,
                    "template": self.stack_template_path,
                    "environment": None
                })

        # Save
        stack.user = self.stack_user_name
        stack.run = self.stack_run
        stack.hook_script = self.hook_script
        stack.hook_events = self.hook_events
        stack.protocol = self.stack_protocol
        stack.port = port
        stack.providers = providers

        stack.save(update_fields=[
            "user",
            "run",
            "hook_script",
            "hook_events",
            "protocol",
            "port",
            "providers"
        ])

        return stack

    def update_stack(self, data):
        """
        Updates a stack in the database with the given data.  Must be invoked
        in a transaction.
        """
        course_id, student_id = self.get_block_ids()
        update_stack(self.stack_name, course_id, student_id, data)

    def get_stack(self, prop=None):
        course_id, student_id = self.get_block_ids()
        return get_stack(self.stack_name, course_id, student_id, prop)

    def launch_stack_task(self, settings, kwargs):
        soft_time_limit = self.get_launch_timeout(settings)
        hard_time_limit = soft_time_limit + 30

        return LaunchStackTask().apply_async(
            kwargs=kwargs,
            expires=soft_time_limit,
            soft_time_limit=soft_time_limit,
            time_limit=hard_time_limit
        )

    def launch_stack_task_result(self, task_id):
        return LaunchStackTask().AsyncResult(task_id)

    @XBlock.json_handler
    @transaction.atomic
    def get_user_stack_status(self, request_data, suffix=''):
        """
        Update the user stack status and return it.

        """
        settings = get_xblock_settings()
        course_id, student_id = self.get_block_ids()
        initialize = request_data.get("initialize", False)
        reset = request_data.get("reset", False)

        stack = Stack.objects.select_for_update().get(
            student_id=student_id,
            course_id=course_id,
            name=self.stack_name
        )

        def _launch_stack(reset=False):
            # Run
            result = self.launch_stack_task(settings, {
                "stack_id": stack.id,
                "reset": reset
            })

            # Update stack
            stack.status = LAUNCH_PENDING
            stack.error_msg = ""
            stack.launch_task_id = result.id
            stack.launch_timestamp = timezone.now()

            logger.info("Fired async launch task [%s] for [%s]" % (
                result.id, self.stack_name))

            return result

        def _check_result(result):
            if result and result.ready() and not result.successful():
                raise LaunchError(repr(result.result))

        if stack.status in DOWN_STATES or not stack.status:
            # Launch the stack if there's no known status, or if it's known to
            # be down.
            logger.info("Launching stack [%s] with previous status [%s]." %
                        (self.stack_name, stack.status))
            try:
                _check_result(_launch_stack(reset))
            except LaunchError as e:
                stack.status = LAUNCH_ERROR
                stack.error_msg = e.error_msg
        elif stack.status in UP_STATES:
            # The stack is up.  Reset it, if requested.
            if reset:
                logger.info("Resetting successfully launched stack [%s]." %
                            (self.stack_name))
                try:
                    _check_result(_launch_stack(reset))
                except LaunchError as e:
                    stack.status = LAUNCH_ERROR
                    stack.error_msg = e.error_msg

            else:
                logger.info("Successful launch detected for [%s], "
                            "with status [%s]" %
                            (self.stack_name, stack.status))
        elif stack.status == LAUNCH_PENDING:
            # The stack is pending launch.
            try:
                # Check if the Celery task hasn't blown up.
                task_id = stack.launch_task_id
                _check_result(self.launch_stack_task_result(task_id))
            except LaunchError as e:
                stack.status = LAUNCH_ERROR
                stack.error_msg = e.error_msg
            else:
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
                    logger.debug("Launch pending for [%s]" % (self.stack_name))

                elif initialize or reset:
                    # Timeout reached, but the user just entered the page or
                    # requested a reset.  Try launching the stack again.
                    if initialize:
                        logger.info("Launch timeout detected on initialize. "
                                    "Launching stack [%s]" % (self.stack_name))
                    else:
                        logger.info("Launch timeout detected on reset. "
                                    "Resetting stack [%s]" % (self.stack_name))
                    try:
                        _check_result(_launch_stack(reset))
                    except LaunchError as e:
                        stack.status = LAUNCH_ERROR
                        stack.error_msg = e.error_msg
                else:
                    # Timeout reached.  Consider the task a failure and let the
                    # user retry manually.
                    logger.error("Launch timeout reached for [%s] "
                                 "after %s seconds" % (self.stack_name,
                                                       time_since_launch))
                    stack.status = LAUNCH_ERROR
                    stack.error_msg = "Timeout when launching stack."
        elif stack.status in PENDING_STATES:
            # The stack is otherwise pending.  Report and let the user retry
            # manually.
            logger.error("Detected pending stack [%s], "
                         "with status [%s]" % (self.stack_name,
                                               stack.status))
        elif initialize or reset:
            # Detected an unforeseen state, but the user just entered the page,
            # or requested a retry or reset, so start from scratch.
            if reset:
                logger.info("Resetting failed stack [%s]." %
                            (self.stack_name))
            else:
                logger.info("Retrying previously failed stack [%s]." %
                            (self.stack_name))
            try:
                _check_result(_launch_stack(reset))
            except LaunchError as e:
                stack.status = LAUNCH_ERROR
                stack.error_msg = e.error_msg
        else:
            # Detected a failed stack.  Report the error and let the user retry
            # manually.
            logger.error("Failed stack [%s] detected with status [%s]." %
                         (self.stack_name, stack.status))

        # Reset the dead man's switch
        stack.suspend_timestamp = timezone.now()

        # Save changes to the database
        stack.save()

        return {
            "status": stack.status,
            "error_msg": stack.error_msg,
            "ip": stack.ip,
            "user": stack.user,
            "key": stack.key,
            "password": stack.password
        }

    @XBlock.json_handler
    @transaction.atomic
    def keepalive(self, data, suffix=''):
        """
        Reset the dead man's switch.

        """
        self.update_stack({"suspend_timestamp": timezone.now()})

    @XBlock.json_handler
    @transaction.atomic
    def set_port(self, data, suffix=''):
        """
        Set the preferred stack port

        """
        self.update_stack({"port": int(data.get("port"))})

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
