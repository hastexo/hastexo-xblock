from keystoneclient.auth.identity import v2 as v2_auth
from keystoneclient.auth.identity import v3 as v3_auth
from keystoneclient import discover
from keystoneclient.openstack.common.apiclient import exceptions as ks_exc
from keystoneclient import session as kssession
from heatclient import client as heat_client
from heatclient import exc as heat_exc
from six.moves.urllib import parse as urlparse

class HeatWrapper(object):
    def __init__(self):
        self.service_type = 'orchestration'
        self.endpoint_type = 'publicURL'
        self.api_version = '1'

    def get_client(self, auth_url, **kwargs):
        region_name = kwargs.pop('region_name', None)
        username = kwargs.get('username', None)
        password = kwargs.get('password', None)

        # Authenticate with Keystone
        keystone_session = kssession.Session()
        keystone_auth = self._get_keystone_auth(keystone_session, auth_url, **kwargs)

        # Get the Heat endpoint
        endpoint = keystone_auth.get_endpoint(keystone_session,
                                              service_type=self.service_type,
                                              interface=self.endpoint_type,
                                              region_name=region_name)

        # Initiate the Heat client
        heat_kwargs = {'auth_url': auth_url,
                       'session': keystone_session,
                       'auth': keystone_auth,
                       'service_type': self.service_type,
                       'endpoint_type': self.endpoint_type,
                       'region_name': region_name,
                       'username': username,
                       'password': password}

        return heat_client.Client(self.api_version, endpoint, **heat_kwargs)

    def _get_keystone_auth(self, session, auth_url, **kwargs):
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
            user_domain_name = kwargs.get('user_domain_name', None)
            user_domain_id = kwargs.get('user_domain_id', None)
            project_domain_name = kwargs.get('project_domain_name', None)
            project_domain_id = kwargs.get('project_domain_id', None)

            if (user_domain_name or user_domain_id or project_domain_name or
                    project_domain_id):
                auth = self._get_keystone_v3_auth(v3_auth_url, **kwargs)
            else:
                auth = self._get_keystone_v2_auth(v2_auth_url, **kwargs)
        elif v3_auth_url:
            auth = self._get_keystone_v3_auth(v3_auth_url, **kwargs)
        elif v2_auth_url:
            auth = self._get_keystone_v2_auth(v2_auth_url, **kwargs)
        else:
            raise heat_exc.CommandError('Unable to determine Keystone version.')

        return auth

    def _get_keystone_v3_auth(self, v3_auth_url, **kwargs):
        auth_token = kwargs.pop('auth_token', None)
        if auth_token:
            return v3_auth.Token(v3_auth_url, auth_token)
        else:
            return v3_auth.Password(v3_auth_url, **kwargs)

    def _get_keystone_v2_auth(self, v2_auth_url, **kwargs):
        auth_token = kwargs.pop('auth_token', None)
        tenant_id = kwargs.get('project_id', None)
        tenant_name = kwargs.get('project_name', None)
        if auth_token:
            return v2_auth.Token(v2_auth_url, auth_token,
                                 tenant_id=tenant_id,
                                 tenant_name=tenant_name)
        else:
            username=kwargs.get('username', None)
            password=kwargs.get('password', None)
            return v2_auth.Password(v2_auth_url,
                                    username=username,
                                    password=password,
                                    tenant_id=tenant_id,
                                    tenant_name=tenant_name)

