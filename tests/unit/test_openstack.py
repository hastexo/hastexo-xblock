from unittest import TestCase
from mock import patch, Mock
from hastexo.openstack import OpenStackWrapper, HeatWrapper, NovaWrapper


class TestOpenStackWrapper(TestCase):
    def setUp(self):
        self.credentials = {
            "os_auth_url": "bogus_auth_url",
            "os_auth_token": "bogus_auth_token",
            "os_username": "bogus_username",
            "os_password": "bogus_password",
            "os_user_id": "bogus_user_id",
            "os_user_domain_id": "bogus_user_domain_id",
            "os_user_domain_name": "bogus_user_domain_name",
            "os_project_id": "bogus_project_id",
            "os_project_name": "bogus_project_name",
            "os_project_domain_id": "bogus_project_domain_id",
            "os_project_domain_name": "bogus_project_domain_name",
            "os_region_name": "bogus_region_name"
        }
        patchers = {
            "generic": patch("hastexo.openstack.generic"),
            "kssession": patch("hastexo.openstack.kssession"),
            "heat_client": patch("hastexo.openstack.heat_client"),
            "nova_client": patch("hastexo.openstack.nova_client")
        }
        self.mocks = {}
        for mock_name, patcher in patchers.items():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)

    def test_init(self):
        wrapper = OpenStackWrapper(**self.credentials)
        for key in self.credentials:
            self.assertEqual(self.credentials[key], wrapper.options[key])

    def test_get_keystone_auth_with_token(self):
        wrapper = OpenStackWrapper(**self.credentials)
        _, _ = wrapper.get_keystone_auth()
        self.mocks["kssession"].Session.assert_called()
        self.mocks["generic"].Token.assert_called_with(
            token=self.credentials['os_auth_token'],
            auth_url=self.credentials['os_auth_url']
        )

    def test_get_keystone_auth_without_token(self):
        self.credentials["os_auth_token"] = ""
        wrapper = OpenStackWrapper(**self.credentials)
        _, _ = wrapper.get_keystone_auth()
        self.mocks["kssession"].Session.assert_called()
        self.mocks["generic"].Token.assert_not_called()
        self.mocks["generic"].Password.assert_called_with(
            username=self.credentials['os_username'],
            user_id=self.credentials['os_user_id'],
            user_domain_id=self.credentials['os_user_domain_id'],
            user_domain_name=self.credentials['os_user_domain_name'],
            password=self.credentials['os_password'],
            auth_url=self.credentials['os_auth_url'],
            project_id=self.credentials['os_project_id'],
            project_name=self.credentials['os_project_name'],
            project_domain_id=self.credentials['os_project_domain_id'],
            project_domain_name=self.credentials['os_project_domain_name'],
        )

    def test_get_keystone_auth_with_tenant_creds(self):
        self.credentials["os_auth_token"] = ""
        self.credentials['os_tenant_id'] = self.credentials['os_project_id']
        self.credentials['os_tenant_name'] = \
            self.credentials['os_project_name']
        self.credentials['os_project_id'] = ""
        self.credentials['os_project_name'] = ""
        wrapper = OpenStackWrapper(**self.credentials)
        _, _ = wrapper.get_keystone_auth()
        self.mocks["kssession"].Session.assert_called()
        self.mocks["generic"].Token.assert_not_called()
        self.mocks["generic"].Password.assert_called_with(
            username=self.credentials['os_username'],
            user_id=self.credentials['os_user_id'],
            user_domain_id=self.credentials['os_user_domain_id'],
            user_domain_name=self.credentials['os_user_domain_name'],
            password=self.credentials['os_password'],
            auth_url=self.credentials['os_auth_url'],
            project_id=self.credentials['os_tenant_id'],
            project_name=self.credentials['os_tenant_name'],
            project_domain_id=self.credentials['os_project_domain_id'],
            project_domain_name=self.credentials['os_project_domain_name'],
        )


class TestHeatWrapper(TestOpenStackWrapper):
    def test_init(self):
        wrapper = HeatWrapper(**self.credentials)
        self.assertEqual(wrapper.service_type, 'orchestration')
        self.assertEqual(wrapper.endpoint_type, 'publicURL')
        self.assertEqual(wrapper.api_version, '1')

    def test_get_client(self):
        wrapper = HeatWrapper(**self.credentials)
        mock_get_keystone_auth = Mock(return_value=("sess", "auth"))
        with patch.multiple(
                wrapper,
                get_keystone_auth=mock_get_keystone_auth):
            wrapper.get_client()
        self.mocks["heat_client"].Client.called_with(
            "1",
            auth_url=self.credentials['os_auth_url'],
            session="sess",
            auth="auth",
            service_type="orchestration",
            endpoint_type="publicURL",
            region_name=self.credentials['os_region_name'],
            username=self.credentials['os_username'],
            password=self.credentials['os_password']
        )


class TestNovaWrapper(TestOpenStackWrapper):
    def test_init(self):
        wrapper = NovaWrapper(**self.credentials)
        self.assertEqual(wrapper.service_type, 'compute')
        self.assertEqual(wrapper.endpoint_type, 'publicURL')
        self.assertEqual(wrapper.api_version, '2.0')

    def test_get_client(self):
        wrapper = NovaWrapper(**self.credentials)
        mock_get_keystone_auth = Mock(return_value=("sess", "auth"))
        with patch.multiple(
                wrapper,
                get_keystone_auth=mock_get_keystone_auth):
            wrapper.get_client()
        self.mocks["nova_client"].Client.called_with(
            "2.0",
            self.credentials['os_username'],
            self.credentials['os_password'],
            project_id=self.credentials['os_project_id'],
            project_name=self.credentials['os_project_name'],
            user_id=self.credentials['os_user_id'],
            auth_url=self.credentials['os_auth_url'],
            region_name=self.credentials['os_region_name'],
            endpoint_type="publicURL",
            service_type="compute",
            session="sess",
            auth="auth",
            project_domain_id=self.credentials['os_project_domain_id'],
            project_domain_name=self.credentials['os_project_domain_name'],
            user_domain_id=self.credentials['os_user_domain_id'],
            user_domain_name=self.credentials['os_user_domain_name']
        )
