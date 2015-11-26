import json
import logging
import textwrap

from .tasks import launch_or_resume_user_stack as launch_or_resume_user_stack_task
from .tasks import suspend_user_stack as suspend_user_stack_task
from .tasks import check as check_task

from xblock.core import XBlock
from xblock.fields import Scope, Integer, Float, String, Dict, List
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xmodule.contentstore.content import StaticContent
from xmodule.contentstore.django import contentstore

log = logging.getLogger(__name__)
loader = ResourceLoader(__name__)


class HastexoXBlock(StudioEditableXBlockMixin, XBlock):
    """
    Provides lab environments and an SSH connection to them.
    """

    # Scope: content.  These are set per course.
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
        help="The OpenStack authentication URL")
    os_tenant_name = String(
        default="",
        scope=Scope.content,
        help="The OpenStack tenant name")
    os_username = String(
        default="",
        scope=Scope.content,
        help="The OpenStack user name")
    os_password = String(
        default="",
        scope=Scope.content,
        help="The OpenStack password")
    tests = List(
        default=[],
        scope=Scope.content,
        help="The list of tests to run.")

    # Scope: settings.  These are set per instance.
    display_name = String(
        default="Lab",
        scope=Scope.settings,
        help="Title to display")
    weight = Float(
        default=1,
        scope=Scope.settings,
        help="Defines the maximum total grade of the block.")

    # Scope: user state.  These are set per instance, per user.
    os_heat_template = String(
        default="",
        scope=Scope.user_state,
        help="The user stack orchestration template")
    user_stack_name = String(
        default="",
        scope=Scope.user_state,
        help="The name of the user's stack")
    user_stack_launch_id = String(
        default="",
        scope=Scope.user_state,
        help="The user stack launch task id")
    user_stack_suspend_id = String(
        default="",
        scope=Scope.user_state,
        help="The user stack suspend task id")
    user_stack_status = Dict(
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
        'stack_user_name',
        'os_auth_url',
        'os_tenant_name',
        'os_username',
        'os_password')

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

                log.info('Test: %s' % text)
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

    def launch_or_resume_user_stack(self, sync = False):
        """
        Launches the student stack if it doesn't exist, resume it if it does
        and is suspended.
        """
        kwargs = {'stack_name': self.user_stack_name,
                  'stack_user_name': self.stack_user_name,
                  'os_auth_url': self.os_auth_url,
                  'os_username': self.os_username,
                  'os_password': self.os_password,
                  'os_tenant_name': self.os_tenant_name,
                  'os_heat_template': self.os_heat_template}

        # Synchronous or asynchronous?
        if sync:
            result = launch_or_resume_user_stack_task.apply(kwargs=kwargs)
        else:
            result = launch_or_resume_user_stack_task.apply_async(kwargs=kwargs)
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
        kwargs = {'stack_name': self.user_stack_name,
                  'os_auth_url': self.os_auth_url,
                  'os_username': self.os_username,
                  'os_password': self.os_password,
                  'os_tenant_name': self.os_tenant_name}
        result = suspend_user_stack_task.apply_async(kwargs=kwargs, countdown=120)
        self.user_stack_suspend_id = result.id

    def check(self):
        kwargs = {'tests': self.tests,
                  'stack_ip': self.user_stack_status['ip'],
                  'stack_name': self.user_stack_name,
                  'stack_user_name': self.stack_user_name}
        result = check_task.apply_async(kwargs=kwargs)
        self.check_id = result.id

        # Store the result
        self._save_check_task_result(result)

    def student_view(self, context=None):
        """
        The primary view of the HastexoXBlock, shown to students when viewing
        courses.
        """
        # Get the anonymous user id
        user_id = self.xmodule_runtime.anonymous_student_id
        course_id = self.xmodule_runtime.course_id
        course_code = course_id.course
        self.user_stack_name = "%s_%s" % (course_code, user_id)

        # Load the stack template from the course's content store
        loc = StaticContent.compute_location(course_id, self.stack_template_path)
        asset = contentstore().find(loc)
        self.os_heat_template = asset.data

        # Make sure the user's stack is launched...
        self.launch_or_resume_user_stack()

        # ...and immediately start a dead man's switch to suspend it in due
        # time.
        self.suspend_user_stack()

        # Render the HTML template
        html_context = {}
        html = loader.render_template('static/html/main.html', html_context)
        frag = Fragment(html)

        # Add the public CSS and JS
        frag.add_css_url(self.runtime.local_resource_url(self, 'public/css/main.css'))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/js/main.js'))

        # Choose the JS initialization function
        frag.initialize_js('HastexoXBlock')

        return frag

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
            result = launch_or_resume_user_stack_task.AsyncResult(self.user_stack_launch_id)
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
            res = {'status': 'PENDING'}
        # If a check task is running, return its status.
        elif self.check_id:
            result = check_task.AsyncResult(self.check_id)
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
