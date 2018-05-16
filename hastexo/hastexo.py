import time
import logging
import textwrap

from xblock.core import XBlock
from xblock.fields import Scope, Float, String, Dict, List, Integer
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xblockutils.settings import XBlockWithSettingsMixin

from django.db import transaction
from django.utils import timezone

from .models import Stack
from .utils import (UP_STATES, LAUNCH_STATE, LAUNCH_ERROR_STATE, SETTINGS_KEY,
                    DEFAULT_SETTINGS, get_xblock_configuration)
from .tasks import LaunchStackTask, CheckStudentProgressTask

logger = logging.getLogger(__name__)
loader = ResourceLoader(__name__)


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
    stack_ports = List(
        default=[],
        scope=Scope.settings,
        help="What ports are available in the stack.")
    stack_port_names = List(
        default=[],
        scope=Scope.settings,
        help="Names of ports defined above.")
    provider = String(
        default="default",
        scope=Scope.settings,
        help="Where to launch the stack.")

    # Set exclusively via XML
    tests = List(
        default=[],
        scope=Scope.content,
        help="The list of tests to run.")

    # User state, per instance.
    stack_run = String(
        default="",
        scope=Scope.user_state,
        help="The name of the run")
    stack_name = String(
        default="",
        scope=Scope.user_state,
        help="The name of the user's stack")
    check_id = String(
        default="",
        scope=Scope.user_state,
        help="The check task id")
    check_timestamp = Integer(
        default="",
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
        'stack_ports',
        'stack_port_names',
        'provider')

    has_author_view = True
    has_score = True
    has_children = True
    icon_class = 'problem'
    block_settings_key = SETTINGS_KEY

    @classmethod
    def parse_xml(cls, node, runtime, keys, id_generator):
        block = runtime.construct_xblock_from_class(cls, keys)

        # Find <test> children
        for child in node:
            if child.tag == "test":
                text = child.text

                # Fix up whitespace.
                if text[0] == "\n":
                    text = text[1:]
                text.rstrip()
                text = textwrap.dedent(text)

                block.tests.append(text)
            else:
                block.runtime.add_node_as_child(block, child, id_generator)

        # Attributes become fields.
        for name, value in node.items():
            if name in block.fields:
                value = (block.fields[name]).from_string(value)
                setattr(block, name, value)

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

    def get_stack_template(self):
        """
        Load the stack template directly from the course's content store.

        Note: accessing the contentstore directly is not supported by the
        XBlock API, so this depends on keeping pace with changes to
        edx-platform itself.  Because of it, this should be replaced with an
        HTTP GET to the LMS, in the future.

        """
        course_id, _ = self.get_block_ids()
        stack_template = None
        try:
            from xmodule.contentstore.content import StaticContent
            from xmodule.contentstore.django import contentstore
            from xmodule.exceptions import NotFoundError

            loc = StaticContent.compute_location(course_id,
                                                 self.stack_template_path)
            asset = contentstore().find(loc)
            stack_template = asset.data
        except (ImportError, NotFoundError):
            pass

        return stack_template

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
        configuration = self.get_configuration()

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

        # Set the port
        port = None
        if len(self.stack_ports) > 0:
            port = self.stack_get("port")
            if not port or port not in self.stack_ports:
                port = self.stack_ports[0]

        # Update stack info
        self.stack_update({
            "provider": self.provider,
            "protocol": self.stack_protocol,
            "port": port
        })

        # Call the JS initialization function
        frag.initialize_js('HastexoXBlock', {
            "terminal_url": configuration.get("terminal_url"),
            "timeouts": configuration.get("js_timeouts"),
            "has_tests": len(self.tests) > 0,
            "protocol": self.stack_protocol,
            "ports": self.stack_ports,
            "port_names": self.stack_port_names,
            "port": port,
            "provider": self.provider
        })

        return frag

    def get_configuration(self):
        """
        Get the configuration data for the student_view.

        """
        settings = self.get_xblock_settings(default=DEFAULT_SETTINGS)
        return get_xblock_configuration(settings, self.provider)

    @transaction.atomic()
    def stack_update(self, data):
        course_id, student_id = self.get_block_ids()
        stack, _ = Stack.objects.select_for_update().get_or_create(
            student_id=student_id,
            course_id=course_id,
            name=self.stack_name
        )
        for (field, value) in data.items():
            if hasattr(stack, field):
                setattr(stack, field, value)
        stack.save()

    @transaction.atomic()
    def stack_get(self, prop=None):
        course_id, student_id = self.get_block_ids()
        stack, _ = Stack.objects.select_for_update().get_or_create(
            student_id=student_id,
            course_id=course_id,
            name=self.stack_name
        )

        if prop:
            return getattr(stack, prop)
        else:
            return stack

    def reset_suspend_timestamp(self):
        self.stack_update({"suspend_timestamp": timezone.now()})

    def launch_stack_task(self, args):
        configuration = args[0]
        task = LaunchStackTask()
        soft_time_limit = configuration.get('launch_timeout')
        time_limit = soft_time_limit + 30
        result = task.apply_async(
            args=args,
            expires=soft_time_limit,
            soft_time_limit=soft_time_limit,
            time_limit=time_limit
        )
        logger.info(
            'Launch task id for '
            'stack [%s] is: [%s]' % (self.stack_name, result.id)
        )

        return result

    def launch_stack_task_result(self, task_id):
        return LaunchStackTask().AsyncResult(task_id)

    @XBlock.json_handler
    def get_user_stack_status(self, request_data, suffix=''):
        configuration = self.get_configuration()

        def _launch_stack(reset=False):
            args = (
                configuration,
                self.stack_run,
                self.stack_name,
                self.get_stack_template(),
                self.stack_user_name,
                reset
            )

            logger.info('Firing async launch '
                        'task for [%s]' % (self.stack_name))
            result = self.launch_stack_task(args)

            # Save task ID and timestamp
            self.stack_update({
                "launch_task_id": result.id,
                "launch_timestamp": timezone.now()
            })

            return result

        def _process_result(result):
            if result.ready():
                if (result.successful() and
                        isinstance(result.result, dict) and not
                        result.result.get('error')):
                    data = result.result
                else:
                    data = {
                        "status": LAUNCH_ERROR_STATE,
                        "error_msg": "Unexpected result: %s" % repr(result.result)  # noqa: E501
                    }
            else:
                data = {"status": LAUNCH_STATE}

            # Save status
            self.stack_update(data)

            return data

        def _process_stack_data(stack):
            data = {
                "status": stack.status,
                "error_msg": stack.error_msg,
                "ip": stack.ip,
                "user": stack.user,
                "key": stack.key,
                "password": stack.password
            }

            return data

        def _process_error(error_msg):
            data = {
                "status": LAUNCH_ERROR_STATE,
                "error_msg": error_msg
            }

            # Save status
            self.stack_update(data)

            return data

        # Fetch the stack
        stack = self.stack_get()

        # Calculate the time since the suspend timer was last reset.
        suspend_timeout = configuration.get("suspend_timeout")
        suspend_timestamp = stack.suspend_timestamp
        time_since_suspend = 0
        if suspend_timeout and suspend_timestamp:
            time_since_suspend = (timezone.now() - suspend_timestamp).seconds

        # Request type
        initialize = request_data.get("initialize", False)
        reset = request_data.get("reset", False)

        # Get the last stack status
        prev_status = stack.status

        # No last stack status: this is the first time
        # the user launches this stack.
        if not prev_status:
            logger.info('Launching stack [%s] '
                        'for the first time.' % (self.stack_name))
            result = _launch_stack(reset)
            stack_data = _process_result(result)

        # There was a previous attempt at launching the stack
        elif prev_status == LAUNCH_STATE:
            # Update task result
            launch_task_id = self.stack_get("launch_task_id")
            result = self.launch_stack_task_result(launch_task_id)
            stack_data = _process_result(result)
            current_status = stack_data.get("status")

            # Stack is still LAUNCH_STATE since last check.
            if current_status == LAUNCH_STATE:
                # Calculate time since launch
                launch_timestamp = self.stack_get("launch_timestamp")
                time_since_launch = (timezone.now() - launch_timestamp).seconds
                launch_timeout = configuration.get("launch_timeout")

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
                    result = _launch_stack(reset)
                    stack_data = _process_result(result)

                else:
                    # Timeout reached.  Consider the task a failure and let the
                    # user retry manually.
                    logger.error('Launch timeout reached for [%s] '
                                 'after %s seconds' % (self.stack_name,
                                                       time_since_launch))
                    stack_data = _process_error("Timeout when launching "
                                                "or resuming stack.")

            # Stack changed from LAUNCH_STATE to COMPLETE.
            elif current_status in UP_STATES:
                if reset or (suspend_timeout and time_since_suspend >= suspend_timeout):  # noqa: E501
                    if reset:
                        logger.info('Resetting successfully launched '
                                    'stack [%s].' % (self.stack_name))
                    else:
                        logger.info('Stack [%s] may have suspended. '
                                    'Relaunching.' % (self.stack_name))
                    result = _launch_stack(reset)
                    stack_data = _process_result(result)

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
                result = _launch_stack(reset)
                stack_data = _process_result(result)

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
                result = _launch_stack(reset)
                stack_data = _process_result(result)

            else:
                logger.info('Successful launch detected for [%s], '
                            'with status [%s]' % (self.stack_name,
                                                  prev_status))
                stack_data = _process_stack_data(stack)

        # Detected a failed launch attempt, but the user just entered the page,
        # or requested a retry or reset, so start from scratch.
        elif initialize or reset:
            if reset:
                logger.info('Resetting failed stack [%s].' % (self.stack_name))
            else:
                logger.info('Retrying previously failed '
                            'stack [%s].' % (self.stack_name))
            result = _launch_stack(reset)
            stack_data = _process_result(result)

        # Detected a failed launch attempt.  Report the error and let the user
        # retry manually.
        else:
            logger.error('Failed launch detected for [%s], '
                         'with status [%s]' % (self.stack_name,
                                               prev_status))
            stack_data = _process_stack_data(stack)

        # Reset the dead man's switch
        self.reset_suspend_timestamp()

        return stack_data

    @XBlock.json_handler
    def keepalive(self, data, suffix=''):
        # Reset the dead man's switch
        self.reset_suspend_timestamp()

    def check_progress_task(self, args):
        configuration = args[0]
        task = CheckStudentProgressTask()
        soft_time_limit = configuration.get('check_timeout')
        time_limit = soft_time_limit + 30
        result = task.apply_async(
            args=args,
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
        configuration = self.get_configuration()

        def _launch_check():
            stack = self.stack_get()
            logger.info('Executing tests for stack [%s], IP [%s], user [%s]:' %
                        (self.stack_name, stack.ip,
                         self.stack_user_name))
            for test in self.tests:
                logger.info('Test: %s' % test)

            args = (
                configuration,
                self.tests,
                stack.ip,
                self.stack_user_name,
                stack.key
            )
            result = self.check_progress_task(args)

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
                check_timeout = configuration.get("check_timeout")

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
        self.stack_update({"port": int(data.get("port"))})

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
