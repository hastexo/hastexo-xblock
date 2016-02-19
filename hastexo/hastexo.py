import json
import logging
import textwrap
import markdown2

from xblock.core import XBlock
from xblock.fields import Scope, Integer, Float, String, Dict, List
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xmodule.contentstore.content import StaticContent
from xmodule.contentstore.django import contentstore
from xmodule.exceptions import NotFoundError
from opaque_keys import InvalidKeyError

from .tasks import LaunchStackTask, SuspendStackTask, CheckStudentProgressTask

log = logging.getLogger(__name__)
loader = ResourceLoader(__name__)


class HastexoXBlock(StudioEditableXBlockMixin, XBlock):
    """
    Provides lab environments and an SSH connection to them.
    """

    # Scope: content.
    instructions_path = String(
        default="",
        scope=Scope.content,
        help="The relative path to the markdown lab instructions.  For example, \"markdown_lab.md\".")
    stack_template_path = String(
        default="",
        scope=Scope.content,
        help="The relative path to the uploaded orchestration template.  For example, \"hot_lab.yaml\".")
    stack_user_name = String(
        default="",
        scope=Scope.content,
        help="The name of the training user in the stack.")
    os_auth_url = String(
        default="",
        scope=Scope.content,
        help="The OpenStack authentication URL.")
    os_auth_token = String(
        default="",
        scope=Scope.content,
        help="The OpenStack authentication token.")
    os_username = String(
        default="",
        scope=Scope.content,
        help="The OpenStack user name.")
    os_password = String(
        default="",
        scope=Scope.content,
        help="The OpenStack password.")
    os_user_id = String(
        default="",
        scope=Scope.content,
        help="The OpenStack user ID. (v3 API)")
    os_user_domain_id = String(
        default="",
        scope=Scope.content,
        help="The OpenStack user domain ID. (v3 API)")
    os_user_domain_name = String(
        default="",
        scope=Scope.content,
        help="The OpenStack user domain name. (v3 API)")
    os_project_id = String(
        default="",
        scope=Scope.content,
        help="The OpenStack project ID. (v3 API)")
    os_project_name = String(
        default="",
        scope=Scope.content,
        help="The OpenStack project name. (v3 API)")
    os_project_domain_id = String(
        default="",
        scope=Scope.content,
        help="The OpenStack project domain ID. (v3 API)")
    os_project_domain_name = String(
        default="",
        scope=Scope.content,
        help="The OpenStack project domain name. (v3 API)")
    os_region_name = String(
        default="",
        scope=Scope.content,
        help="The OpenStack region name.")
    tests = List(
        default=[],
        scope=Scope.content,
        help="The list of tests to run.")

    # Kept for backwards compatibility.
    os_tenant_id = String(
        default="",
        scope=Scope.content,
        help="The OpenStack tenant ID. (v2.0 API)")
    os_tenant_name = String(
        default="",
        scope=Scope.content,
        help="The OpenStack tenant name. (v2.0 API)")

    # Scope: settings.  These are set per instance.
    display_name = String(
        default="Lab",
        scope=Scope.settings,
        help="Title to display")
    weight = Float(
        default=1,
        scope=Scope.settings,
        help="Defines the maximum total grade of the block.")

    # Scope: preferences.  These are set across blocks in a course.
    user_stack_template = String(
        default="",
        scope=Scope.preferences,
        help="The user stack orchestration template")
    user_stack_name = String(
        default="",
        scope=Scope.preferences,
        help="The name of the user's stack")
    user_stack_launch_id = String(
        default="",
        scope=Scope.preferences,
        help="The user stack launch task id")
    user_stack_suspend_id = String(
        default="",
        scope=Scope.preferences,
        help="The user stack suspend task id")
    user_stack_status = Dict(
        default=None,
        scope=Scope.preferences,
        help="The user stack status")

    # Scope: user state.  These are set per instance, per user.
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
        'stack_user_name',
        'os_auth_url',
        'os_auth_token',
        'os_username',
        'os_password',
        'os_user_id',
        'os_user_domain_id',
        'os_user_domain_name',
        'os_project_id',
        'os_project_name',
        'os_project_domain_id',
        'os_project_domain_name',
        'os_region_name')

    has_author_view = True
    has_score = True
    has_children = True
    icon_class = 'problem'

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
            cls._set_field_if_present(block, name, value)

        return block

    def author_view(self, context=None):
        """ Studio View """
        return Fragment(u'<em>This XBlock only renders content when viewed via the LMS.</em></p>')

    def _save_user_stack_task_result(self, result):
        if result.ready():
            # Clear the task ID so we know there is no task running.
            self.user_stack_launch_id = ""

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
        self.user_stack_status = res
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
        # tenant_name and tenant_id are deprecated
        project_name = self.os_project_name
        if not project_name and self.os_tenant_name:
            project_name = self.os_tenant_name

        project_id = self.os_project_id
        if not project_id and self.os_tenant_id:
            project_id = self.os_tenant_id

        return {'auth_token': self.os_auth_token,
                'username': self.os_username,
                'password': self.os_password,
                'user_id': self.os_user_id,
                'user_domain_id': self.os_user_domain_id,
                'user_domain_name': self.os_user_domain_name,
                'project_id': project_id,
                'project_name': project_name,
                'project_domain_id': self.os_project_domain_id,
                'project_domain_name': self.os_project_domain_name,
                'region_name': self.os_region_name}

    def launch_or_resume_user_stack(self, sync = False):
        """
        Launches the student stack if it doesn't exist, resume it if it does
        and is suspended.
        """
        args = (self.user_stack_name, self.user_stack_template, self.stack_user_name, self.os_auth_url)
        kwargs = self._get_os_auth_kwargs()
        task = LaunchStackTask()
        if sync:
            result = task.apply(args=args, kwargs=kwargs)
        else:
            result = task.apply_async(args=args, kwargs=kwargs, expires=60)
            self.user_stack_launch_id = result.id

        # Store the result
        self._save_user_stack_task_result(result)

    def revoke_suspend(self):
        if self.user_stack_suspend_id:
            from lms import CELERY_APP
            CELERY_APP.control.revoke(self.user_stack_suspend_id)
            self.user_stack_suspend_id = ""

    def suspend_user_stack(self):
        # If the suspend task is pending, revoke it.
        self.revoke_suspend()

        # (Re)schedule the suspension in the future.
        args = (self.user_stack_name, self.os_auth_url)
        kwargs = self._get_os_auth_kwargs()
        result = SuspendStackTask().apply_async(args=args, kwargs=kwargs, countdown=120)
        self.user_stack_suspend_id = result.id

    def check(self):
        log.info('Executing tests for stack [%s], IP [%s], user [%s]:' %
                (self.user_stack_name, self.user_stack_status['ip'],
                 self.stack_user_name))
        for test in self.tests:
            log.info('Test: %s' % test)

        args = (self.tests, self.user_stack_status['ip'], self.user_stack_name,
                self.stack_user_name)
        result = CheckStudentProgressTask().apply_async(args=args, expires=60)
        self.check_id = result.id

        # Store the result
        self._save_check_task_result(result)

    def student_view(self, context=None):
        """
        The primary view of the HastexoXBlock, shown to students when viewing
        courses.
        """
        # Get the course id and anonymous user id, and derive the stack name
        # from them
        user_id = self.xmodule_runtime.anonymous_student_id
        course_id = self.xmodule_runtime.course_id
        course_code = course_id.course
        self.user_stack_name = "%s_%s" % (course_code, user_id)

        # Load the stack template from the course's content store
        loc = StaticContent.compute_location(course_id, self.stack_template_path)
        asset = contentstore().find(loc)
        self.user_stack_template = asset.data

        # Load the instructions and convert from markdown
        instructions = None
        try:
            loc = StaticContent.compute_location(course_id, self.instructions_path)
            asset = contentstore().find(loc)
            instructions = markdown2.markdown(asset.data)
        except (NotFoundError, InvalidKeyError):
            pass

        # Render the HTML template
        html_context = {'instructions': instructions}
        html = loader.render_template('static/html/main.html', html_context)
        frag = Fragment(html)

        # Add the public CSS and JS
        frag.add_css_url(self.runtime.local_resource_url(self, 'public/css/main.css'))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/js/plugins.js'))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/js/main.js'))

        # Choose the JS initialization function
        frag.initialize_js('HastexoXBlock')

        return frag

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
        self.suspend_user_stack()

    @XBlock.json_handler
    def get_user_stack_status(self, data, suffix=''):
        # Stop the dead man's switch
        self.revoke_suspend()

        # If a stack launch task is still pending, check its status.
        if self.user_stack_launch_id:
            result = LaunchStackTask().AsyncResult(self.user_stack_launch_id)
            res = self._save_user_stack_task_result(result)

            # If the launch task was successful, check it synchronously once
            # more: the stack might have been suspended in the meantime.
            status = res.get('status')
            if (status != 'ERROR' and
                status != 'PENDING' and
                status != 'CREATE_FAILED' and
                status != 'RESUME_FAILED'):
                self.launch_or_resume_user_stack(True)
                res = self.user_stack_status

        # If there aren't pending launch tasks, we may need to resume it, so
        # run the async procedure once more.
        else:
            self.launch_or_resume_user_stack()
            res = self.user_stack_status

        # Start the dead man's switch
        self.suspend_user_stack()

        return res

    @XBlock.json_handler
    def get_check_status(self, data, suffix=''):
        """
        Checks the current student score.
        """
        # If a stack launch task is running, return immediately.
        if self.user_stack_launch_id:
            log.info('stack launch task is running: %s' % self.user_stack_launch_id)
            res = {'status': 'PENDING'}
        # If a check task is running, return its status.
        elif self.check_id:
            log.info('check task is running: %s' % self.check_id)
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
