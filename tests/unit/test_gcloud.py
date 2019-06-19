from unittest import TestCase
from mock import patch
from hastexo.gcloud import GcloudDeploymentManager, GcloudComputeEngine


class TestGcloudService(TestCase):
    def setUp(self):
        self.info = {
            "gc_deploymentmanager_api_version": "v2",
            "gc_compute_api_version": "v1",
            "gc_type": "service_account",
            "gc_project_id": "bogus_project",
            "gc_private_key_id": "bogus_key_id",
            "gc_private_key": "bogus_key",
            "gc_client_email": "",
            "gc_client_id": "",
            "gc_auth_uri": "",
            "gc_token_uri": "",
            "gc_auth_provider_x509_cert_url": "",
            "gc_client_x509_cert_url": ""
        }
        patchers = {
            "service_account": patch("hastexo.gcloud.service_account"),
            "build": patch("hastexo.gcloud.build")
        }
        self.mocks = {}
        for mock_name, patcher in patchers.items():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)


class TestGcloudDeploymentManager(TestGcloudService):
    def test_init(self):
        service = GcloudDeploymentManager(**self.info)
        self.assertEqual(self.info["gc_deploymentmanager_api_version"],
                         service.api_version)
        self.assertEqual("deploymentmanager", service.service_name)
        self.assertEqual(service.info["type"], self.info["gc_type"])
        self.assertEqual(service.info["project_id"],
                         self.info["gc_project_id"])
        self.assertEqual(service.info["private_key_id"],
                         self.info["gc_private_key_id"])
        self.assertEqual(service.info["private_key"],
                         self.info["gc_private_key"])
        self.assertEqual(service.info["client_email"],
                         self.info["gc_client_email"])
        self.assertEqual(service.info["client_id"], self.info["gc_client_id"])
        self.assertEqual(service.info["auth_uri"], self.info["gc_auth_uri"])
        self.assertEqual(service.info["token_uri"], self.info["gc_token_uri"])
        self.assertEqual(service.info["auth_provider_x509_cert_url"],
                         self.info["gc_auth_provider_x509_cert_url"])
        self.assertEqual(service.info["client_x509_cert_url"],
                         self.info["gc_client_x509_cert_url"])

    def test_init_with_default_api_version(self):
        self.info.pop("gc_deploymentmanager_api_version")
        service = GcloudDeploymentManager(**self.info)
        self.assertEqual("v2", service.api_version)

    def test_init_with_custom_api_version(self):
        self.info["gc_deploymentmanager_api_version"] = "alpha"
        service = GcloudDeploymentManager(**self.info)
        self.assertEqual("alpha", service.api_version)

    def test_get_service(self):
        service = GcloudDeploymentManager(**self.info)
        service.get_service()
        self.mocks["service_account"].Credentials.from_service_account_info.\
            assert_called()
        self.mocks["build"].assert_called()


class TestGcloudComputeEngine(TestGcloudService):
    def test_init(self):
        service = GcloudComputeEngine(**self.info)
        self.assertEqual(self.info["gc_compute_api_version"],
                         service.api_version)
        self.assertEqual("compute", service.service_name)
        self.assertEqual(service.info["type"], self.info["gc_type"])
        self.assertEqual(service.info["project_id"],
                         self.info["gc_project_id"])
        self.assertEqual(service.info["private_key_id"],
                         self.info["gc_private_key_id"])
        self.assertEqual(service.info["private_key"],
                         self.info["gc_private_key"])
        self.assertEqual(service.info["client_email"],
                         self.info["gc_client_email"])
        self.assertEqual(service.info["client_id"], self.info["gc_client_id"])
        self.assertEqual(service.info["auth_uri"], self.info["gc_auth_uri"])
        self.assertEqual(service.info["token_uri"], self.info["gc_token_uri"])
        self.assertEqual(service.info["auth_provider_x509_cert_url"],
                         self.info["gc_auth_provider_x509_cert_url"])
        self.assertEqual(service.info["client_x509_cert_url"],
                         self.info["gc_client_x509_cert_url"])

    def test_init_with_default_api_version(self):
        self.info.pop("gc_compute_api_version")
        service = GcloudComputeEngine(**self.info)
        self.assertEqual("v1", service.api_version)

    def test_init_with_custom_api_version(self):
        self.info["gc_compute_api_version"] = "beta"
        service = GcloudComputeEngine(**self.info)
        self.assertEqual("beta", service.api_version)

    def test_get_service(self):
        service = GcloudComputeEngine(**self.info)
        service.get_service()
        self.mocks["service_account"].Credentials.from_service_account_info.\
            assert_called()
        self.mocks["build"].assert_called()
