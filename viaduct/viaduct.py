import json
import logging

from .tasks import launch_or_resume_user_stack as async_launch_or_resume_user_stack
from .tasks import suspend_user_stack as async_suspend_user_stack

from xblock.core import XBlock
from xblock.fields import Scope, Integer, String, Dict
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin
from xmodule.contentstore.content import StaticContent
from xmodule.contentstore.django import contentstore

loader = ResourceLoader(__name__)


class ViaductXBlock(StudioEditableXBlockMixin, XBlock):
    """
    Provides lab environments for Viaduct classes.
    """

    # Scope: content
    terminal_href = String(
        default="",
        scope=Scope.content,
        help="Where the terminal server is running")
    template_href = String(
        default="",
        scope=Scope.content,
        help="The path to the orchestration template.  Must be in /c4x/ form.")

    # Scope: settings
    os_auth_url = String(
        default="",
        scope=Scope.settings,
        help="The OpenStack authentication URL")
    os_tenant_name = String(
        default="",
        scope=Scope.settings,
        help="The OpenStack tenant name")
    os_username = String(
        default="",
        scope=Scope.settings,
        help="The OpenStack user name")
    os_password = String(
        default="",
        scope=Scope.settings,
        help="The OpenStack password")

    # Scope: user state
    user_id = String(
        default="",
        scope=Scope.user_state,
        help="The user's anonymous id")
    os_heat_template = String(
        default="",
        scope=Scope.user_state,
        help="The user stack orchestration template")
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

    editable_fields = (
        'terminal_href',
        'template_href',
        'os_auth_url',
        'os_tenant_name',
        'os_username',
        'os_password')

    has_author_view = True

    def author_view(self, context=None):
        """ Studio View """
        return Fragment(u'<p><strong>Viaduct XBlock:</strong> <em>The Viaduct XBlock only renders content when viewed via the LMS.</em></p>')

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

    def launch_or_resume_user_stack(self):
        """
        Launches the student stack if it doesn't exist, resume it if it does
        and is suspended.
        """
        kwargs = {'user_id': self.user_id,
                  'os_auth_url': self.os_auth_url,
                  'os_username': self.os_username,
                  'os_password': self.os_password,
                  'os_tenant_name': self.os_tenant_name,
                  'os_heat_template': self.os_heat_template}
        result = async_launch_or_resume_user_stack.apply_async(kwargs=kwargs)

        # Store the task ID and result
        self.user_stack_launch_id = result.id
        self._save_user_stack_task_result(result)

    def suspend_user_stack(self):
        # If the suspend task is pending, revoke it.
        if self.user_stack_suspend_id:
            from lms import CELERY_APP
            CELERY_APP.control.revoke(self.user_stack_suspend_id)
            self.user_stack_suspend_id = ""

        # (Re)schedule the suspension in the future.
        kwargs = {'user_id': self.user_id,
                  'os_auth_url': self.os_auth_url,
                  'os_username': self.os_username,
                  'os_password': self.os_password,
                  'os_tenant_name': self.os_tenant_name}
        result = async_suspend_user_stack.apply_async(kwargs=kwargs, countdown=120)
        self.user_stack_suspend_id = result.id

    def student_view(self, context=None):
        """
        The primary view of the ViaductXBlock, shown to students when viewing
        courses.
        """
        # Get the anonymous user id
        self.user_id = self.xmodule_runtime.anonymous_student_id

        # Load the template from the course's content store
        asset_key = StaticContent.get_location_from_path(self.template_href)
        asset = contentstore().find(asset_key)
        self.os_heat_template = asset.data

        # Make sure the user's stack is launched...
        self.launch_or_resume_user_stack()

        # ...and immediately start a dead man's switch to suspend it in due
        # time.
        self.suspend_user_stack()

        # Render the HTML template
        html_context = {}
        html = loader.render_template('static/html/viaduct.html', html_context)
        frag = Fragment(html)

        # Add the public CSS and JS
        frag.add_css_url(self.runtime.local_resource_url(self, 'public/css/viaduct.css'))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/js/viaduct.js'))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/js/gateone.js'))

        # Choose the JS initialization function
        frag.initialize_js('ViaductXBlock')

        return frag

    @XBlock.json_handler
    def get_terminal_href(self, data, suffix=''):
        return {'terminal_href': self.terminal_href}

    @XBlock.json_handler
    def keepalive(self, data, suffix=''):
        # Reset the dead man's switch
        self.suspend_user_stack()

    @XBlock.json_handler
    def get_user_stack_status(self, data, suffix=''):
        # Reset the dead man's switch
        self.suspend_user_stack()

        # If a stack launch task is running, check and return its status.
        if self.user_stack_launch_id:
            result = async_launch_or_resume_user_stack.AsyncResult(self.user_stack_launch_id)
            res = self._save_user_stack_task_result(result)

        # If not, and if we have a saved status, return it.
        elif isinstance(self.user_stack_status, dict):
            res = self.user_stack_status

        # Otherwise, report the stack as pending.
        else:
            res = {'status': 'PENDING'}

        return res

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("ViaductXBlock",
             """<vertical_demo>
                <viaduct/>
                </vertical_demo>
             """),
        ]
