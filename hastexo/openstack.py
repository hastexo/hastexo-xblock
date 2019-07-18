from keystoneauth1.identity import generic
from keystoneauth1 import session as kssession
from heatclient import client as heat_client
from novaclient import client as nova_client


class OpenStackWrapper(object):
    """
    A meta-class for wrapping OpenStack services.

    """
    os_options = (
        'os_auth_url',
        'os_auth_token',
        'os_username',
        'os_password',
        'os_user_id',
        'os_user_domain_id',
        'os_user_domain_name',
        'os_tenant_id',
        'os_tenant_name',
        'os_project_id',
        'os_project_name',
        'os_project_domain_id',
        'os_project_domain_name',
        'os_region_name'
    )

    service_type = None
    endpoint_type = None
    api_version = None
    options = {}

    def __init__(self, **options):
        # Set OpenStack options
        for os_option in self.os_options:
            self.options[os_option] = options.get(os_option)

    def get_keystone_auth(self):
        keystone_session = kssession.Session(verify=True)
        if self.options['os_auth_token']:
            kwargs = {
                'token': self.options['os_auth_token'],
                'auth_url': self.options['os_auth_url']
            }
            keystone_auth = generic.Token(**kwargs)
        else:
            project_id = self.options['os_project_id'] or self.options['os_tenant_id']  # noqa: E501
            project_name = self.options['os_project_name'] or self.options['os_tenant_name']  # noqa: E501
            kwargs = {
                'username': self.options['os_username'],
                'user_id': self.options['os_user_id'],
                'user_domain_id': self.options['os_user_domain_id'],
                'user_domain_name': self.options['os_user_domain_name'],
                'password': self.options['os_password'],
                'auth_url': self.options['os_auth_url'],
                'project_id': project_id,
                'project_name': project_name,
                'project_domain_id': self.options['os_project_domain_id'],
                'project_domain_name': self.options['os_project_domain_name'],
            }
            keystone_auth = generic.Password(**kwargs)

        return (keystone_session, keystone_auth)


class HeatWrapper(OpenStackWrapper):
    """
    A class that wraps the Heat service for the Hastexo XBlock.

    """
    def __init__(self, **options):
        self.service_type = 'orchestration'
        self.endpoint_type = 'publicURL'
        self.api_version = '1'

        super(HeatWrapper, self).__init__(**options)

    def get_client(self):
        """
        This function is based, with minor changes, on the official OpenStack
        Heat client's shell implementation.  Specifically,
        python-heatclient/heatclient/shell.py.

        """
        keystone_session, keystone_auth = self.get_keystone_auth()

        kwargs = {
            'auth_url': self.options['os_auth_url'],
            'session': keystone_session,
            'auth': keystone_auth,
            'service_type': self.service_type,
            'endpoint_type': self.endpoint_type,
            'region_name': self.options['os_region_name'],
            'username': self.options['os_username'],
            'password': self.options['os_password']
        }

        return heat_client.Client(self.api_version, **kwargs)


class NovaWrapper(OpenStackWrapper):
    """
    A class that wraps the Compute service for the Hastexo XBlock.

    """
    def __init__(self, **options):
        self.service_type = 'compute'
        self.endpoint_type = 'publicURL'
        self.api_version = '2.0'

        super(NovaWrapper, self).__init__(**options)

    def get_client(self):
        keystone_session, keystone_auth = self.get_keystone_auth()
        return nova_client.Client(
            self.api_version,
            self.options['os_username'],
            self.options['os_password'],
            project_id=self.options['os_project_id'],
            project_name=self.options['os_project_name'],
            user_id=self.options['os_user_id'],
            auth_url=self.options['os_auth_url'],
            region_name=self.options['os_region_name'],
            endpoint_type=self.endpoint_type,
            service_type=self.service_type,
            session=keystone_session,
            auth=keystone_auth,
            project_domain_id=self.options['os_project_domain_id'],
            project_domain_name=self.options['os_project_domain_name'],
            user_domain_id=self.options['os_user_domain_id'],
            user_domain_name=self.options['os_user_domain_name'])
