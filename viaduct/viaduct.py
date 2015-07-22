from xblock.core import XBlock
from xblock.fields import Scope, Integer, String
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader

loader = ResourceLoader(__name__)

class ViaductXBlock(XBlock):
    """
    Provides lab environments for Viaduct classes.
    """

    # Scope: content
    gateone_url = String(
            default="https://127.0.0.1",
            scope=Scope.content,
            help="Where the gateone server is running")

    os_heat_template = String(
            default=None,
            scope=Scope.content,
            help="The OpenStack Heat template")

    # Scope: settings
    os_auth_url = String(
            default=None,
            scope=Scope.settings,
            help="The OpenStack authentication URL")
    os_tenant_name = String(
            default=None,
            scope=Scope.settings,
            help="The OpenStack tenant name")
    os_user_name = String(
            default=None,
            scope=Scope.settings,
            help="The OpenStack user name")
    os_password = String(
            default=None,
            scope=Scope.settings,
            help="The OpenStack password")
    os_heat_flavor = String(
            default=None,
            scope=Scope.settings,
            help="The OpenStack Heat flavor")
    os_heat_public_net_id = String(
            default=None,
            scope=Scope.settings,
            help="The OpenStack Heat public net ID")
    os_heat_image = String(
            default=None,
            scope=Scope.settings,
            help="The OpenStack Heat image")

    # Scope: user state
    public_ip = String(
            default=None,
            scope=Scope.user_state,
            help="The user environment's public IP")

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
