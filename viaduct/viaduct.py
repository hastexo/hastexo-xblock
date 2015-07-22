from xblock.core import XBlock
from xblock.fields import Scope, Integer, String
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin

loader = ResourceLoader(__name__)


class ViaductXBlock(StudioEditableXBlockMixin, XBlock):
    """
    Provides lab environments for Viaduct classes.
    """

    # Scope: content
    gateone_url = String(
        default="https://127.0.0.1",
        scope=Scope.content,
        help="Where the gateone server is running")
    os_heat_template = String(
        multiline_editor=True,
        resettable_editor=False,
        default="",
        scope=Scope.content,
        help="The OpenStack Heat template")

    # Scope: settings
    os_auth_url = String(
        default="",
        scope=Scope.settings,
        help="The OpenStack authentication URL")
    os_tenant_name = String(
        default="",
        scope=Scope.settings,
        help="The OpenStack tenant name")
    os_user_name = String(
        default="",
        scope=Scope.settings,
        help="The OpenStack user name")
    os_password = String(
        default="",
        scope=Scope.settings,
        help="The OpenStack password")

    # Scope: user state

    editable_fields = (
        'gateone_url',
        'os_heat_template',
        'os_auth_url',
        'os_tenant_name',
        'os_user_name',
        'os_password',
        'os_password')

    def student_view(self, context=None):
        """
        The primary view of the ViaductXBlock, shown to students
        when viewing courses.
        """
        # Render the HTML template
        html_context = {}
        html = loader.render_template('static/html/viaduct.html', html_context)
        frag = Fragment(html)

        # Add the public CSS and JS
        frag.add_css_url(self.runtime.local_resource_url(self, 'public/css/viaduct.css'))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/js/gateone.js'))

        # Render the custom JS
        js_context = {'gateone_url': self.gateone_url}
        js = loader.render_template('static/js/src/viaduct.js', js_context)
        frag.add_javascript(js)

        # Choose the JS initialization function
        frag.initialize_js('ViaductXBlock')

        return frag

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
