import json
import logging
import textwrap
import markdown2
import time

from xblock.core import XBlock
from xblock.fields import Scope, Boolean, Integer, Float, String, Dict, List
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xblockutils.settings import XBlockWithSettingsMixin
from xmodule.contentstore.content import StaticContent
from xmodule.contentstore.django import contentstore
from xmodule.exceptions import NotFoundError
from opaque_keys import InvalidKeyError

from .tasks import LaunchStackTask, SuspendStackTask, CheckStudentProgressTask

logger = logging.getLogger(__name__)
loader = ResourceLoader(__name__)


@XBlock.wants('settings')
class HastexoXBlock(XBlock, XBlockWithSettingsMixin, StudioEditableXBlockMixin):
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
        help="The relative path to the uploaded orchestration template.  For example, \"hot_lab.yaml\".")
    stack_user_name = String(
        scope=Scope.settings,
        help="The name of the training user in the stack.")

    # Not used: only set here for backward compatibility.  They are now set via
    # XBlock settings exclusively.
    launch_timeout = Integer(
        scope=Scope.settings,
        help="How long to wait for a launch task, in seconds")
    suspend_timeout = Integer(
        scope=Scope.settings,
        help="How long to wait until stack is suspended, in seconds")
    terminal_url = String(
        scope=Scope.settings,
        help="Where the terminal server is running.")
    os_auth_url = String(
        scope=Scope.settings,
        help="The OpenStack authentication URL.")
    os_auth_token = String(
        scope=Scope.settings,
        help="The OpenStack authentication token.")
    os_username = String(
        scope=Scope.settings,
        help="The OpenStack user name.")
    os_password = String(
        scope=Scope.settings,
        help="The OpenStack password.")
    os_user_id = String(
        scope=Scope.settings,
        help="The OpenStack user ID. (v3 API)")
    os_user_domain_id = String(
        scope=Scope.settings,
        help="The OpenStack user domain ID. (v3 API)")
    os_user_domain_name = String(
        scope=Scope.settings,
        help="The OpenStack user domain name. (v3 API)")
    os_project_id = String(
        scope=Scope.settings,
        help="The OpenStack project ID. (v3 API)")
    os_project_name = String(
        scope=Scope.settings,
        help="The OpenStack project name. (v3 API)")
    os_project_domain_id = String(
        scope=Scope.settings,
        help="The OpenStack project domain ID. (v3 API)")
    os_project_domain_name = String(
        scope=Scope.settings,
        help="The OpenStack project domain name. (v3 API)")
    os_region_name = String(
        scope=Scope.settings,
        help="The OpenStack region name.")
    os_tenant_id = String(
        scope=Scope.settings,
        help="The OpenStack tenant ID. (v2.0 API)")
    os_tenant_name = String(
        scope=Scope.settings,
        help="The OpenStack tenant name. (v2.0 API)")

    # Optional
    instructions_path = String(
        scope=Scope.settings,
        help="The relative path to the markdown lab instructions.  For example, \"markdown_lab.md\".")

    # Set exclusively via XML
    tests = List(
        default=[],
        scope=Scope.content,
        help="The list of tests to run.")

    # User state, per instance.
    configuration = Dict(
        scope=Scope.user_state,
        default={},
        help="Runtime configuration")
    stack_template = String(
        default="",
        scope=Scope.user_state,
        help="The user stack orchestration template")
    stack_name = String(
        default="",
        scope=Scope.user_state,
        help="The name of the user's stack")
    check_id = String(
        default="",
        scope=Scope.user_state,
        help="The check task id")
    check_status = Dict(
        default=None,
        scope=Scope.user_state,
        help="The check status")

    # Stack states per user, across all courses
    stacks = Dict(
        default={},
        scope=Scope.preferences,
        help="Stack states for this user's courses: one entry per stack")

    editable_fields = (
        'display_name',
        'weight',
        'stack_template_path',
        'stack_user_name')

    has_author_view = True
    has_score = True
    has_children = True
    icon_class = 'problem'
    block_settings_key = 'hastexo'

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
        return Fragment(u'<em>This XBlock only renders content when viewed via the LMS.</em></p>')

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

    def student_view(self, context=None):
        """
        The primary view of the HastexoXBlock, shown to students when viewing
        courses.
        """
        # Load configuration
        self.configuration = self.get_configuration()

        # Get the course id and anonymous user id, and derive the stack name
        # from them
        user_id = self.xmodule_runtime.anonymous_student_id
        course_id = self.xmodule_runtime.course_id
        course_code = course_id.course
        self.stack_name = "%s_%s" % (course_code, user_id)

        def error_out(msg):
            context = {'error_msg': msg}
            html = loader.render_template('static/html/error.html', context)
            frag = Fragment(html)
            frag.add_css_url(self.runtime.local_resource_url(self, 'public/css/main.css'))
            return frag

        # Load the stack template from the course's content store
        try:
            loc = StaticContent.compute_location(course_id, self.stack_template_path)
            asset = contentstore().find(loc)
            self.stack_template = asset.data
        except NotFoundError as detail:
            return error_out('Stack template not found: {0}'.format(detail))

        # Load the instructions and convert from markdown
        instructions = None
        try:
            loc = StaticContent.compute_location(course_id, self.instructions_path)
            asset = contentstore().find(loc)
            instructions = markdown2.markdown(asset.data)
        except (NotFoundError, InvalidKeyError, AttributeError):
            pass

        # Render the HTML template
        html_context = {'instructions': instructions}
        html = loader.render_template('static/html/main.html', html_context)
        frag = Fragment(html)

        # Add the public CSS and JS
        frag.add_css_url(self.runtime.local_resource_url(self, 'public/css/main.css'))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/js/plugins.js'))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/js/main.js'))

        # Call the JS initialization function
        frag.initialize_js('HastexoXBlock', {
            "terminal_url": self.configuration.get("terminal_url"),
            "timeouts": self.configuration.get("js_timeouts")
        })

        return frag

    def get_configuration(self):
        """
        Get the configuration data for the student_view.

        """
        defaults = {
            "launch_timeout": 300,
            "suspend_timeout": 120,
            "terminal_url": "/terminal",
            "ssh_dir": "/edx/var/edxapp/terminal_users/ANONYMOUS/.ssh",
            "ssh_upload": False,
            "ssh_bucket": "identities",
            "task_timeouts": {
                "sleep": 5,
                "retries": 60
            },
            "js_timeouts": {
                "status": 10000,
                "keepalive": 15000,
                "idle": 600000,
                "check": 5000
            }
        }

        settings = self.get_xblock_settings(default=defaults)

        # Set defaults
        launch_timeout = settings.get("launch_timeout", defaults["launch_timeout"])
        suspend_timeout = settings.get("suspend_timeout", defaults["suspend_timeout"])
        terminal_url = settings.get("terminal_url", defaults["terminal_url"])
        ssh_dir = settings.get("ssh_dir", defaults["ssh_dir"])
        ssh_upload = settings.get("ssh_upload", defaults["ssh_upload"])
        ssh_bucket = settings.get("ssh_bucket", defaults["ssh_bucket"])
        task_timeouts = settings.get("task_timeouts", defaults["task_timeouts"])
        js_timeouts = settings.get("js_timeouts", defaults["js_timeouts"])

        # tenant_name and tenant_id are deprecated
        os_project_name = settings.get("os_project_name")
        if not os_project_name and settings.get("os_tenant_name"):
            os_project_name = settings.get("os_tenant_name")

        os_project_id = settings.get("os_project_id")
        if not os_project_id and settings.get("os_tenant_id"):
            os_project_id = settings.get("os_tenant_id")

        return {
            "launch_timeout": launch_timeout,
            "suspend_timeout": suspend_timeout,
            "terminal_url": terminal_url,
            "ssh_dir": ssh_dir,
            "ssh_upload": ssh_upload,
            "ssh_bucket": ssh_bucket,
            "task_timeouts": task_timeouts,
            "js_timeouts": js_timeouts,
            "os_auth_url": settings.get("os_auth_url"),
            "os_auth_token": settings.get("os_auth_token"),
            "os_username": settings.get("os_username"),
            "os_password": settings.get("os_password"),
            "os_user_id": settings.get("os_user_id"),
            "os_user_domain_id": settings.get("os_user_domain_id"),
            "os_user_domain_name": settings.get("os_user_domain_name"),
            "os_project_id": os_project_id,
            "os_project_name": os_project_name,
            "os_project_domain_id": settings.get("os_project_domain_id"),
            "os_project_domain_name": settings.get("os_project_domain_name"),
            "os_region_name": settings.get("os_region_name")
        }

    def stack_set(self, prop, value):
        if not self.stacks.get(self.stack_name):
            self.stacks[self.stack_name] = {}

        self.stacks[self.stack_name][prop] = value

    def stack_get(self, l1 = None, l2 = None):
        retval = self.stacks.get(self.stack_name)
        if retval and l1:
            retval = retval.get(l1)
            if retval and l2:
                retval = retval.get(l2)

        return retval

    def get_os_auth_kwargs(self):
        return {
            'auth_token': self.configuration.get('os_auth_token'),
            'username': self.configuration.get('os_username'),
            'password': self.configuration.get('os_password'),
            'user_id': self.configuration.get('os_user_id'),
            'user_domain_id': self.configuration.get('os_user_domain_id'),
            'user_domain_name': self.configuration.get('os_user_domain_name'),
            'project_id': self.configuration.get('os_project_id'),
            'project_name': self.configuration.get('os_project_name'),
            'project_domain_id': self.configuration.get('os_project_domain_id'),
            'project_domain_name': self.configuration.get('os_project_domain_name'),
            'region_name': self.configuration.get('os_region_name')
        }

    def suspend_user_stack(self):
        suspend_timeout = self.configuration.get("suspend_timeout")
        if suspend_timeout:
            # If the suspend task is pending, revoke it.
            stack_suspend_id = self.stack_get("suspend_id")
            if stack_suspend_id:
                logger.info('Revoking suspend task for [%s]' % (self.stack_name))
                from lms import CELERY_APP
                CELERY_APP.control.revoke(stack_suspend_id)
                self.stack_set("suspend_id", None)

            # (Re)schedule the suspension in the future.
            args = (self.configuration, self.stack_name, self.configuration.get('os_auth_url'))
            kwargs = self.get_os_auth_kwargs()
            task = SuspendStackTask()
            logger.info('Scheduling suspend task for [%s] in %s seconds' % (self.stack_name, suspend_timeout))
            result = task.apply_async(args=args,
                                      kwargs=kwargs,
                                      countdown=suspend_timeout)
            self.stack_set("suspend_id", result.id)
            self.stack_set("suspend_timestamp", int(time.time()))

    @XBlock.json_handler
    def get_user_stack_status(self, data, suffix=''):
        # Calculate the time since the suspend timer was last reset.
        now = int(time.time())
        suspend_timeout = self.configuration.get("suspend_timeout")
        suspend_timestamp = self.stack_get("suspend_timestamp")
        time_since_suspend = 0
        if suspend_timeout and suspend_timestamp:
            time_since_suspend = now - suspend_timestamp

        # Get the last stack status
        last_status_string = ""
        last_status = self.stack_get("status")
        if last_status:
            last_status_string = last_status.get("status", "")

        def _launch_stack():
            args = (
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user_name,
                self.configuration.get('os_auth_url'))
            kwargs = self.get_os_auth_kwargs()

            logger.info('Firing async launch task for [%s]' % (self.stack_name))
            task = LaunchStackTask()
            result = task.apply_async(args=args, kwargs=kwargs,
                    expires=self.configuration.get('launch_timeout'))

            logger.info('Launch task id for stack [%s] is: [%s]' % (self.stack_name, result.id))

            # Save task ID and timestamp
            self.stack_set("launch_id", result.id)
            self.stack_set("launch_timestamp", int(time.time()))

            return result

        def _process_result(result):
            if result.ready():
                if (result.successful() and
                        isinstance(result.result, dict) and not
                        result.result.get('error')):
                    status = result.result
                else:
                    status = {
                        "status": "ERROR",
                        "error_msg": "Unexpected result: %s" % repr(result.result)
                    }
            else:
                status = {"status": "PENDING"}

            # Save status
            self.stack_set("status", status)

            return status

        def _process_error(error_msg):
            status = {
                "status": "ERROR",
                "error_msg": error_msg
            }

            # Save status
            self.stack_set("status", status)

            return status

        # No last stack status: this is the first time the user launches this stack.
        if not last_status_string:
            logger.info('Launching/resuming stack [%s]' % (self.stack_name))
            result = _launch_stack()
            status = _process_result(result)

        # The stack was previously launched successfully
        elif "COMPLETE" in last_status_string:
            # Is it reasonable to assume the stack hasn't been suspended since the last check?
            if not suspend_timeout or time_since_suspend < suspend_timeout:
                logger.info('Successful launch detected for [%s], with status [%s]' % (self.stack_name, last_status_string))
                status = last_status

            # The stack could have been suspended (or deleted) since the last check, so recheck.
            else:
                logger.info('Stack [%s] may have suspended.  Relaunching.' % (self.stack_name))
                result = _launch_stack()
                status = _process_result(result)

        # There was a previous attempt at launching the stack
        elif "PENDING" in last_status_string:
            # Update task result
            result = LaunchStackTask().AsyncResult(self.stack_get("launch_id"))
            status = _process_result(result)

            current_status_string = status.get('status')

            # Stack changed from PENDING to COMPLETE.
            if "COMPLETE" in current_status_string:
                # The stack couldn't have been suspended, yet.
                if not suspend_timeout or time_since_suspend < suspend_timeout:
                    logger.info('Successful launch detected for [%s], with status [%s]' % (self.stack_name, current_status_string))

                # The stack could have been suspended (or deleted) since the last check, so recheck.
                else:
                    logger.info('Stack [%s] may have suspended.  Relaunching.' % (self.stack_name))
                    result = _launch_stack()
                    status = _process_result(result)

            # Stack is still PENDING since last check.
            elif "PENDING" in current_status_string:
                # Calculate time since launch
                launch_timestamp = self.stack_get("launch_timestamp")
                time_since_launch = now - launch_timestamp
                launch_timeout = self.configuration.get('launch_timeout')

                # Check if the pending task hasn't timed out.
                if time_since_launch <= launch_timeout:
                    # The pending task still has some time to finish.  Please wait.
                    logger.info('Launch pending for [%s]' % (self.stack_name))

                elif data["initialize"]:
                    # Timeout reached, but the user just entered the page.
                    # Try launching the stack again.
                    logger.info('Launching/resuming stack [%s]' % (self.stack_name))
                    result = _launch_stack()
                    status = _process_result(result)

                else:
                    # Timeout reached.  Consider the task a failure and let the
                    # user retry manually.
                    logger.error('Launch timeout reached for [%s] after %s seconds' % (self.stack_name, time_since_launch))
                    status = _process_error("Timeout when launching or resuming stack.")

            # Detected a failed launch attempt, but the user has requested a retry,
            # or just entered the page, so start from scratch.
            elif data["initialize"]:
                logger.info('Launching/resuming stack [%s]' % (self.stack_name))
                result = _launch_stack()
                status = _process_result(result)

            # Detected a failed launch attempt.  Report the error and let the user
            # retry manually.
            else:
                logger.error('Failed launch detected for [%s], with status [%s]' % (self.stack_name, current_status_string))

        # Detected a failed launch attempt, but the user has requested a retry,
        # or just entered the page, so start from scratch.
        elif data["initialize"]:
            logger.info('Launching/resuming stack [%s]' % (self.stack_name))
            result = _launch_stack()
            status = _process_result(result)

        # Detected a failed launch attempt.  Report the error and let the user
        # retry manually.
        else:
            logger.error('Failed launch detected for [%s], with status [%s]' % (self.stack_name, last_status_string))

        # Restart the dead man's switch, if necessary.
        self.suspend_user_stack()

        return status

    @XBlock.json_handler
    def keepalive(self, data, suffix=''):
        # Restart the dead man's switch, if necessary.
        self.suspend_user_stack()

    @XBlock.json_handler
    def get_check_status(self, data, suffix=''):
        """
        Checks the current student score.
        """
        def _launch_check():
            stack_ip = self.stack_get("status", "ip")
            logger.info('Executing tests for stack [%s], IP [%s], user [%s]:' %
                       (self.stack_name, stack_ip,
                        self.stack_user_name))
            for test in self.tests:
                logger.info('Test: %s' % test)

            args = (
                self.configuration,
                self.tests,
                stack_ip,
                self.stack_name,
                self.stack_user_name
            )
            result = CheckStudentProgressTask().apply_async(args=args, expires=60)

            # Save task ID
            self.check_id = result.id

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
                        'error_msg': 'Unexpected result: %s' % repr(result.result)
                    }
            else:
                status = {'status': 'PENDING'}

            # Store the result
            self.check_status = status

            return status

        # If a check task is running, return its status.
        if self.check_id:
            logger.info('check task is running: %s' % self.check_id)
            result = CheckStudentProgressTask().AsyncResult(self.check_id)
            status = _process_result(result)

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
