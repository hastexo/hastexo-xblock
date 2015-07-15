import pkg_resources

from xblock.core import XBlock
from xblock.fields import Scope, Integer, String
from xblock.fragment import Fragment


class ViaductXBlock(XBlock):
    """
    Provides lab environments for Viaduct classes.
    """

    # Scope: content
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


    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None):
        """
        The primary view of the ViaductXBlock, shown to students
        when viewing courses.
        """
        html = self.resource_string("static/html/viaduct.html")
        frag = Fragment(html.format(self=self))
        frag.add_css(self.resource_string("static/css/viaduct.css"))
        frag.add_javascript(self.resource_string("static/js/src/gateone.js"))
        frag.add_javascript(self.resource_string("static/js/src/viaduct.js"))
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
