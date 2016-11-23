from keystoneclient.auth.identity import v2 as v2_auth
from keystoneclient.auth.identity import v3 as v3_auth
from keystoneclient import discover
from keystoneclient.openstack.common.apiclient import exceptions as ks_exc
from keystoneclient import session as kssession
from heatclient import client as heat_client
from heatclient import exc as heat_exc
from six.moves.urllib import parse as urlparse

class HeatWrapper(object):
    """
    A class that wraps the Heat service for the Hastexo XBlock.

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

    options = {}

    def __init__(self, **configuration):
        self.service_type = 'orchestration'
        self.endpoint_type = 'publicURL'
        self.api_version = '1'

        # Set OpenStack options
        options = configuration.get("credentials")
        for os_option in self.os_options:
            self.options[os_option] = options.get(os_option)

    def get_client(self):
        auth_url = self.options.get("os_auth_url")
        region_name = self.options.get("os_region_name")

        # Authenticate with Keystone
        keystone_session = kssession.Session()
        keystone_auth = self._get_keystone_auth(keystone_session, auth_url)

        # Get the Heat endpoint
        endpoint = keystone_auth.get_endpoint(
            keystone_session,
            service_type=self.service_type,
            interface=self.endpoint_type,
            region_name=region_name
        )

        # Initiate the Heat client
        return heat_client.Client(
            self.api_version,
            endpoint,
            auth_url=auth_url,
            session=keystone_session,
            auth=keystone_auth,
            service_type=self.service_type,
            endpoint_type=self.endpoint_type,
            region_name=region_name,
            username=self.options.get("os_username"),
            password=self.options.get("os_password")
        )

    def _get_keystone_auth(self, session, auth_url):
        """
        Figure out whether to use v2 or v3 of the Keystone API, and return the auth
        object.

        This function is based, with minor changes, on the official OpenStack Heat
        client's shell implementation.  Specifically,
        python-heatclient/heatclient/shell.py.
        """
        v2_auth_url = None
        v3_auth_url = None
        try:
            ks_discover = discover.Discover(session=session, auth_url=auth_url)
            v2_auth_url = ks_discover.url_for('2.0')
            v3_auth_url = ks_discover.url_for('3.0')
        except ks_exc.ClientException:
            # If discovery is not supported, parse version out of the auth URL.
            url_parts = urlparse.urlparse(auth_url)
            (scheme, netloc, path, params, query, fragment) = url_parts
            path = path.lower()
            if path.startswith('/v3'):
                v3_auth_url = auth_url
            elif path.startswith('/v2'):
                v2_auth_url = auth_url
            else:
                raise heat_exc.CommandError('Unable to determine Keystone version.')

        auth = None
        if v3_auth_url and v2_auth_url:
            # Both v2 and v3 are supported. Use v3 only if domain information is
            # provided.
            user_domain_name = self.options.get("os_user_domain_name")
            user_domain_id = self.options.get("os_user_domain_id")
            project_domain_name = self.options.get("os_project_domain_name")
            project_domain_id = self.options.get("os_project_domain_id")

            if (user_domain_name or user_domain_id or project_domain_name or
                    project_domain_id):
                auth = self._get_keystone_v3_auth(v3_auth_url)
            else:
                auth = self._get_keystone_v2_auth(v2_auth_url)
        elif v3_auth_url:
            auth = self._get_keystone_v3_auth(v3_auth_url)
        elif v2_auth_url:
            auth = self._get_keystone_v2_auth(v2_auth_url)
        else:
            raise heat_exc.CommandError('Unable to determine Keystone version.')

        return auth

    def _get_keystone_v3_auth(self, auth_url):
        auth_token = self.options.get("os_auth_token")
        if auth_token:
            return v3_auth.Token(auth_url, auth_token)
        else:
            return v3_auth.Password(
                auth_url,
                username=self.options.get("os_username"),
                password=self.options.get("os_password"),
                user_id=self.options.get("os_user_id"),
                user_domain_id=self.options.get("os_user_domain_id"),
                user_domain_name=self.options.get("os_user_domain_name"),
                project_id=self.options.get("os_project_id"),
                project_name=self.options.get("os_project_name"),
                project_domain_id=self.options.get("os_project_domain_id"),
                project_domain_name=self.options.get("os_project_domain_name")
            )

    def _get_keystone_v2_auth(self, auth_url):
        auth_token = self.options.get("os_auth_token")
        tenant_id = self.options.get("os_project_id")
        tenant_name = self.options.get("os_project_name")
        if auth_token:
            return v2_auth.Token(
                auth_url,
                auth_token,
                tenant_id=tenant_id,
                tenant_name=tenant_name
            )
        else:
            return v2_auth.Password(
                auth_url,
                username=self.options.get("os_username"),
                password=self.options.get("os_password"),
                tenant_id=tenant_id,
                tenant_name=tenant_name
            )
