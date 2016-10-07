import json
import logging
import textwrap
import markdown2
import datetime
import pytz

from xblock.core import XBlock
from xblock.fields import Scope, Boolean, Integer, Float, String, Dict, List, DateTime
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

    # User state.
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
    stack_launch_id = String(
        default="",
        scope=Scope.user_state,
        help="The user stack launch task id")
    stack_launch_timestamp = DateTime(
        default=None,
        scope=Scope.user_state,
        help="The user stack launch task timestamp")
    stack_suspend_id = String(
        default="",
        scope=Scope.user_state,
        help="The user stack suspend task id")
    stack_status = Dict(
        default=None,
        scope=Scope.user_state,
        help="The user stack status")
    check_id = String(
        default="",
        scope=Scope.user_state,
        help="The check task id")
    check_status = Dict(
        default=None,
        scope=Scope.user_state,
        help="The check status")

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

    def _save_user_stack_task_result(self, result):
        logger.info('Saving stack result id [%s]: [%s]' % (result.id, result.result))
        if result.ready():
            # Clear the task ID so we know there is no task running.
            self.stack_launch_id = ""
            self.stack_launch_timestamp = None

            if (result.successful() and
                    isinstance(result.result, dict) and not
                    result.result.get('error')):
                res = result.result
            else:
                res = {'status': 'ERROR',
                       'error_msg': 'Unexpected result: %s' % repr(result.result)}
        else:
            res = {'status': 'PENDING'}

        # Store the result
        self.stack_status = res
        return res

    def _save_check_task_result(self, result):
        if result.ready():
            # Clear the task ID so we know there is no task running.
            self.check_id = ""

            if (result.successful() and
                    isinstance(result.result, dict) and not
                    result.result.get('error')):
                res = result.result

                # Publish the grade
                self.runtime.publish(self, 'grade', {
                    'value': res['pass'],
                    'max_value': res['total']
                })
            else:
                res = {'status': 'ERROR',
                       'error_msg': 'Unexpected result: %s' % repr(result.result)}
        else:
            res = {'status': 'PENDING'}

        # Store the result
        self.check_status = res
        return res

    def _get_os_auth_kwargs(self):
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

    def launch_or_resume_user_stack(self, sync = False):
        """
        Launches the student stack if it doesn't exist, resume it if it does
        and is suspended.
        """
        args = (
            self.configuration,
            self.stack_name,
            self.stack_template,
            self.stack_user_name,
            self.configuration.get('os_auth_url'))
        kwargs = self._get_os_auth_kwargs()
        task = LaunchStackTask()
        if sync:
            logger.info('Running synchronous launch task for [%s]' % (self.stack_name))
            result = task.apply(args=args, kwargs=kwargs)
        else:
            logger.info('Firing async launch task for [%s]' % (self.stack_name))
            result = task.apply_async(args=args, kwargs=kwargs,
                    expires=self.configuration.get('launch_timeout'))
            logger.info('Launch task id for stack [%s] is: [%s]' % (self.stack_name, result.id))
            self.stack_launch_id = result.id
            self.stack_launch_timestamp = datetime.datetime.now(pytz.utc)

        # Store the result
        self._save_user_stack_task_result(result)

    def revoke_suspend(self):
        if self.stack_suspend_id:
            logger.info('Revoking suspend tasks for [%s]' % (self.stack_name))
            from lms import CELERY_APP
            CELERY_APP.control.revoke(self.stack_suspend_id)
            self.stack_suspend_id = ""

    def suspend_user_stack(self):
        # If the suspend task is pending, revoke it.
        self.revoke_suspend()

        # (Re)schedule the suspension in the future.
        args = (self.configuration, self.stack_name, self.configuration.get('os_auth_url'))
        kwargs = self._get_os_auth_kwargs()
        task = SuspendStackTask()
        suspend_timeout = self.configuration.get("suspend_timeout")
        logger.info('Scheduling suspend task for [%s] in %s seconds' % (self.stack_name, suspend_timeout))
        result = task.apply_async(args=args,
                                  kwargs=kwargs,
                                  countdown=suspend_timeout)
        self.stack_suspend_id = result.id

    def check(self):
        logger.info('Executing tests for stack [%s], IP [%s], user [%s]:' %
                   (self.stack_name, self.stack_status['ip'],
                    self.stack_user_name))
        for test in self.tests:
            logger.info('Test: %s' % test)

        args = (
            self.configuration,
            self.tests,
            self.stack_status['ip'],
            self.stack_name,
            self.stack_user_name
        )
        result = CheckStudentProgressTask().apply_async(args=args, expires=60)
        self.check_id = result.id

        # Store the result
        self._save_check_task_result(result)

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

        # Load the stack template from the course's content store
        loc = StaticContent.compute_location(course_id, self.stack_template_path)
        asset = contentstore().find(loc)
        self.stack_template = asset.data

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

    @XBlock.json_handler
    def keepalive(self, data, suffix=''):
        # Reset the dead man's switch
        if self.configuration.get("suspend_timeout"):
            self.suspend_user_stack()

    @XBlock.json_handler
    def get_user_stack_status(self, data, suffix=''):
        # Stop the dead man's switch
        self.revoke_suspend()

        # If a stack launch task is still pending, check its status.
        if self.stack_launch_id:
            logger.info('Launch task ID [%s] found for [%s]' % (self.stack_launch_id, self.stack_name))
            if self.stack_launch_timestamp:
                delta = datetime.datetime.now(pytz.utc) - self.stack_launch_timestamp
                if delta.seconds <= self.configuration.get('launch_timeout'):
                    result = LaunchStackTask().AsyncResult(self.stack_launch_id)
                    res = self._save_user_stack_task_result(result)

                    # If the launch task was successful, check it synchronously once
                    # more: the stack might have been suspended in the meantime.
                    status = res.get('status')
                    if (status != 'ERROR' and
                        status != 'PENDING' and
                        status != 'CREATE_FAILED' and
                        status != 'RESUME_FAILED'):
                        logger.info('Successful launch detected for [%s], with status [%s]' % (self.stack_name, status))
                        self.launch_or_resume_user_stack(True)
                        res = self.stack_status
                    elif ('PENDING' in status):
                        logger.info('Launch pending for [%s]' % (self.stack_name))
                    else:
                        logger.error('Failed launch detected for [%s], with status [%s]' % (self.stack_name, status))
                else:
                    # Timeout reached.  Consider the previous task a failure,
                    # and report it as such.
                    logger.error('Launch timeout reached for [%s] after %s seconds' % (self.stack_name, delta.seconds))
                    res = {'status': 'ERROR',
                           'error_msg': 'Timeout when launching or resuming stack.'}
                    self.stack_launch_id = ""
                    self.stack_launch_timestamp = None
                    self.stack_status = res
            else:
                # No timestamp recorded.  Consider the previous task a failure,
                # and report it as such.
                logger.error('Stack launch task found for [%s], but no launch timestamp recorded' % (self.stack_name))
                res = {'status': 'ERROR',
                       'error_msg': 'Timeout when launching or resuming stack.'}
                self.stack_launch_id = ""
                self.stack_status = res

        # If there aren't pending launch tasks, we may need to resume it, so
        # run the async procedure once more.
        else:
            logger.info('Initializing stack launch task for [%s]' % (self.stack_name))
            self.launch_or_resume_user_stack()
            res = self.stack_status

        # Start the dead man's switch
        if self.configuration.get("suspend_timeout"):
            self.suspend_user_stack()

        return res

    @XBlock.json_handler
    def get_check_status(self, data, suffix=''):
        """
        Checks the current student score.
        """
        # If a stack launch task is running, return immediately.
        if self.stack_launch_id:
            logger.info('stack launch task is running: %s' % self.stack_launch_id)
            res = {'status': 'PENDING'}
        # If a check task is running, return its status.
        elif self.check_id:
            logger.info('check task is running: %s' % self.check_id)
            result = CheckStudentProgressTask().AsyncResult(self.check_id)
            res = self._save_check_task_result(result)
        # Otherwise, launch the check task.
        else:
            self.check()
            res = self.check_status

        return res

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
