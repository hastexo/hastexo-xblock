import ddt
import yaml
import base64

from unittest import TestCase
from mock import Mock, patch, call
from heatclient import exc as heat_exc
from keystoneauth1.exceptions import http as keystone_exc
from novaclient import exceptions as nova_exc
from googleapiclient import errors as gcloud_exc

from hastexo.common import b
from hastexo.provider import (Provider, OpenstackProvider, GcloudProvider,
                              ProviderException)


HEAT_EXCEPTIONS = [
    heat_exc.HTTPBadRequest,
    heat_exc.HTTPUnauthorized,
    heat_exc.HTTPForbidden,
    heat_exc.HTTPMethodNotAllowed,
    heat_exc.HTTPConflict,
    heat_exc.HTTPOverLimit,
    heat_exc.HTTPUnsupported,
    heat_exc.HTTPInternalServerError,
    heat_exc.HTTPNotImplemented,
    heat_exc.HTTPBadGateway,
    heat_exc.HTTPServiceUnavailable,
    keystone_exc.BadRequest,
    keystone_exc.Unauthorized,
    keystone_exc.PaymentRequired,
    keystone_exc.Forbidden,
    keystone_exc.NotFound,
    keystone_exc.MethodNotAllowed,
    keystone_exc.NotAcceptable,
    keystone_exc.ProxyAuthenticationRequired,
    keystone_exc.RequestTimeout,
    keystone_exc.Conflict,
    keystone_exc.Gone,
    keystone_exc.LengthRequired,
    keystone_exc.PreconditionFailed,
    keystone_exc.RequestEntityTooLarge,
    keystone_exc.RequestUriTooLong,
    keystone_exc.UnsupportedMediaType,
    keystone_exc.RequestedRangeNotSatisfiable,
    keystone_exc.ExpectationFailed,
    keystone_exc.UnprocessableEntity,
    keystone_exc.InternalServerError,
    keystone_exc.HttpNotImplemented,
    keystone_exc.BadGateway,
    keystone_exc.ServiceUnavailable,
    keystone_exc.GatewayTimeout,
    keystone_exc.HttpVersionNotSupported
]

NOVA_EXCEPTIONS = [
    nova_exc.BadRequest,
    nova_exc.Unauthorized,
    nova_exc.Forbidden,
    nova_exc.NotFound,
    nova_exc.MethodNotAllowed,
    nova_exc.NotAcceptable,
    nova_exc.Conflict,
    nova_exc.OverLimit,
    nova_exc.RateLimit,
    nova_exc.HTTPNotImplemented
]


@ddt.ddt
class TestOpenstackProvider(TestCase):
    def get_heat_client_mock(self):
        return self.mocks["HeatWrapper"].return_value.get_client.return_value

    def get_nova_client_mock(self):
        return self.mocks["NovaWrapper"].return_value.get_client.return_value

    def setUp(self):
        self.stack_name = "bogus_stack_name"
        self.stack_user_name = "bogus_stack_user_name"
        self.stack_ip = "127.0.0.1"
        self.stack_key = u"bogus_stack_key"
        self.stack_password = "bogus_stack_password"
        self.stack_template = "bogus_stack_template"
        self.stack_environment = "bogus_environment"
        self.protocol = "ssh"
        self.port = None
        self.stack_run = "bogus_run"
        self.course_id = "bogus_course_id"
        self.student_id = "bogus_student_id"
        self.provider_name = "bogus_provider"

        # Create a set of mock stacks to be returned by the heat client mock.
        self.stacks = {}
        self.stack_states = (
            "CREATE_IN_PROGRESS",
            "CREATE_FAILED",
            "CREATE_COMPLETE",
            "SUSPEND_IN_PROGRESS",
            "SUSPEND_FAILED",
            "SUSPEND_COMPLETE",
            "RESUME_IN_PROGRESS",
            "RESUME_FAILED",
            "RESUME_COMPLETE",
            "DELETE_IN_PROGRESS",
            "DELETE_FAILED",
            "DELETE_COMPLETE"
        )

        for state in self.stack_states:
            stack = Mock()
            stack.stack_name = "%s_stack" % state.lower()
            stack.stack_status = state
            stack.id = "%s_ID" % state
            stack.outputs = [
                {"output_key": "public_ip",
                 "output_value": self.stack_ip},
                {"output_key": "private_key",
                 "output_value": self.stack_key},
                {"output_key": "password",
                 "output_value": self.stack_password},
                {"output_key": "reboot_on_resume",
                 "output_value": None},
            ]
            self.stacks[state] = stack

        self.mock_provider_config = {
            "type": "openstack",
            "os_auth_url": "bogus_auth_url",
            "os_auth_token": "",
            "os_username": "bogus_username",
            "os_password": "bogus_password",
            "os_user_id": "",
            "os_user_domain_id": "",
            "os_user_domain_name": "",
            "os_project_id": "bogus_project_id",
            "os_project_name": "",
            "os_project_domain_id": "",
            "os_project_domain_name": "",
            "os_region_name": "bogus_region_name"
        }

        # Mock settings
        self.settings = {
            "sleep_timeout": 0,
            "providers": {
                self.provider_name: self.mock_provider_config
            }
        }

        # Patchers
        patchers = {
            "HeatWrapper": patch("hastexo.provider.HeatWrapper"),
            "NovaWrapper": patch("hastexo.provider.NovaWrapper"),
            "settings": patch.dict("hastexo.common.DEFAULT_SETTINGS",
                                   self.settings),
        }
        self.mocks = {}
        for mock_name, patcher in patchers.items():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)

    def test_init(self):
        # Run
        provider = Provider.init(self.provider_name)

        # Assert
        self.assertIsInstance(provider, OpenstackProvider)
        self.assertNotEqual(provider.heat_c, None)
        self.assertNotEqual(provider.nova_c, None)

    def test_no_provider_type_defaults_to_openstack(self):
        # Setup
        self.settings["providers"][self.provider_name].pop("type")

        # Run
        provider = Provider.init(self.provider_name)

        # Assert
        self.assertIsInstance(provider, OpenstackProvider)
        self.assertNotEqual(provider.heat_c, None)
        self.assertNotEqual(provider.nova_c, None)

    def test_list_existing_stacks(self):
        # Setup
        heat = self.get_heat_client_mock()
        mock_stacks = [
            self.stacks["CREATE_COMPLETE"],
            self.stacks["RESUME_COMPLETE"]
        ]
        heat.stacks.list.return_value = mock_stacks

        # Run
        provider = Provider.init(self.provider_name)
        stacks = provider.get_stacks()

        # Assert
        self.assertIsInstance(stacks, list)
        self.assertEqual(len(stacks), 2)
        self.assertEqual(mock_stacks[0].stack_name, stacks[0]["name"])
        self.assertEqual(mock_stacks[1].stack_name, stacks[1]["name"])
        self.assertEqual(mock_stacks[0].stack_status, stacks[0]["status"])
        self.assertEqual(mock_stacks[1].stack_status, stacks[1]["status"])

    def test_list_existing_stacks_empty(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.list.return_value = []

        # Run
        provider = Provider.init(self.provider_name)
        stacks = provider.get_stacks()

        # Assert
        self.assertIsInstance(stacks, list)
        self.assertEqual(len(stacks), 0)

    def test_list_existing_stacks_not_found(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.list.side_effect = heat_exc.HTTPNotFound

        # Run
        provider = Provider.init(self.provider_name)
        stacks = provider.get_stacks()

        # Assert
        self.assertIsInstance(stacks, list)
        self.assertEqual(len(stacks), 0)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_list_existing_stacks_exception(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.list.side_effect = heat_exception

        # Run
        provider = Provider.init(self.provider_name)
        with self.assertRaises(ProviderException):
            provider.get_stacks()

    def test_get_unexistent_stack(self):
        # Setup
        status = "DELETE_COMPLETE"
        mock_stack = self.stacks[status]
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            heat_exc.HTTPNotFound
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.get_stack(mock_stack.id)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual(status, stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        self.assertFalse(stack["outputs"])

    def test_get_existing_stack(self):
        # Setup
        status = "CREATE_COMPLETE"
        mock_stack = self.stacks[status]
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [mock_stack]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.get_stack(mock_stack.id)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual(status, stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password,
            "reboot_on_resume": None,
        }
        self.assertEqual(stack["outputs"], expected_outputs)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_heat_exception_on_get(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            heat_exception
        ]
        status = "CREATE_COMPLETE"
        mock_stack = self.stacks[status]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.get_stack(mock_stack.id)

    def test_create_stack_with_no_template_fails(self):
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.create_stack(self.stack_name, self.stack_run)

    def test_create_stack_success(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.create.side_effect = [
            {"stack": {"id": self.stack_name}}
        ]
        heat.stacks.get.side_effect = [
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_COMPLETE"]
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider.set_template(self.stack_template)
        provider.set_environment(self.stack_environment)
        stack = provider.create_stack(self.stack_name, self.stack_run)

        # Assertions
        self.assertIsInstance(stack, dict)
        self.assertEqual("CREATE_COMPLETE", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password,
            "reboot_on_resume": None,
        }
        self.assertEqual(stack["outputs"], expected_outputs)
        heat.stacks.create.assert_called_with(
            stack_name=self.stack_name,
            template=self.stack_template,
            environment=self.stack_environment,
            parameters={"run": self.stack_run}
        )

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_create_stack_exception_on_create(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.create.side_effect = [
            heat_exception
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_template(self.stack_template)
            provider.create_stack(self.stack_name, self.stack_run)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_create_stack_exception_on_get(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.create.side_effect = [
            {"stack": {"id": self.stack_name}}
        ]
        heat.stacks.get.side_effect = [
            self.stacks["CREATE_IN_PROGRESS"],
            heat_exception
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_template(self.stack_template)
            provider.create_stack(self.stack_name, self.stack_run)

    def test_create_stack_not_found_on_get(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.create.side_effect = [
            {"stack": {"id": self.stack_name}}
        ]
        heat.stacks.get.side_effect = [
            self.stacks["CREATE_IN_PROGRESS"],
            heat_exc.HTTPNotFound
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_template(self.stack_template)
            provider.create_stack(self.stack_name, self.stack_run)

    def test_create_stack_failure(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.create.side_effect = [
            {"stack": {"id": self.stack_name}}
        ]
        heat.stacks.get.side_effect = [
            self.stacks["CREATE_FAILED"]
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_template(self.stack_template)
            provider.create_stack(self.stack_name, self.stack_run)

    def test_resume_stack_with_no_reboots(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["RESUME_IN_PROGRESS"],
            self.stacks["RESUME_IN_PROGRESS"],
            self.stacks["RESUME_COMPLETE"]
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.resume_stack(self.stack_name)

        # Assertions
        self.assertIsInstance(stack, dict)
        self.assertEqual("RESUME_COMPLETE", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password,
            "reboot_on_resume": None,
        }
        self.assertEqual(stack["outputs"], expected_outputs)
        heat.actions.resume.assert_called_with(
            stack_id=self.stack_name
        )

    def test_resume_stack_with_reboots(self):
        # Setup
        mock_stack = self.stacks["RESUME_COMPLETE"]
        servers = ["server1", "server2"]
        mock_stack.outputs = [
            {"output_key": "public_ip",
             "output_value": self.stack_ip},
            {"output_key": "private_key",
             "output_value": self.stack_key},
            {"output_key": "password",
             "output_value": self.stack_password},
            {"output_key": "reboot_on_resume",
             "output_value": servers}
        ]
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        nova = self.get_nova_client_mock()

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.resume_stack(self.stack_name)

        # Assertions
        self.assertIsInstance(stack, dict)
        self.assertEqual("RESUME_COMPLETE", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password,
            "reboot_on_resume": servers,
        }
        self.assertEqual(stack["outputs"], expected_outputs)
        heat.actions.resume.assert_called_with(
            stack_id=self.stack_name
        )
        nova.servers.reboot.assert_has_calls([
            call(servers[0], 'HARD'),
            call(servers[1], 'HARD')
        ])

    @ddt.data(*NOVA_EXCEPTIONS)
    def test_resume_stack_with_nova_exceptions(self, nova_exception):
        # Setup
        mock_stack = self.stacks["RESUME_COMPLETE"]
        servers = ["server1", "server2"]
        mock_stack.outputs = [
            {"output_key": "public_ip",
             "output_value": self.stack_ip},
            {"output_key": "private_key",
             "output_value": self.stack_key},
            {"output_key": "password",
             "output_value": self.stack_password},
            {"output_key": "reboot_on_resume",
             "output_value": servers}
        ]
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        nova = self.get_nova_client_mock()
        nova.servers.reboot.side_effect = [nova_exception("")]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.resume_stack(self.stack_name)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_resume_stack_exception_on_resume(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.actions.resume.side_effect = [
            heat_exception
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.resume_stack(self.stack_name)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_resume_stack_exception_on_get(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["RESUME_IN_PROGRESS"],
            heat_exception
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.resume_stack(self.stack_name)

    def test_resume_stack_not_found_on_get(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["RESUME_IN_PROGRESS"],
            heat_exc.HTTPNotFound
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.resume_stack(self.stack_name)

    def test_resume_stack_failure(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["RESUME_FAILED"]
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.resume_stack(self.stack_name)

    def test_suspend_stack_wait(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["SUSPEND_IN_PROGRESS"],
            self.stacks["SUSPEND_IN_PROGRESS"],
            self.stacks["SUSPEND_COMPLETE"],
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider_stack = provider.suspend_stack(self.stack_name)

        # Assert
        self.assertIsInstance(provider_stack, dict)
        self.assertEqual("SUSPEND_COMPLETE", provider_stack["status"])
        self.assertRaises(KeyError, lambda: provider_stack["outputs"])
        heat.actions.suspend.assert_called_with(stack_id=self.stack_name)

    def test_suspend_stack_disappeared(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["SUSPEND_IN_PROGRESS"],
            heat_exc.HTTPNotFound,
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider_stack = provider.suspend_stack(self.stack_name)

        # Assert
        self.assertIsInstance(provider_stack, dict)
        self.assertEqual("DELETE_COMPLETE", provider_stack["status"])
        self.assertRaises(KeyError, lambda: provider_stack["outputs"])
        heat.actions.suspend.assert_called_with(stack_id=self.stack_name)

    def test_suspend_stack_no_wait(self):
        # Setup
        heat = self.get_heat_client_mock()

        # Run
        provider = Provider.init(self.provider_name)
        provider_stack = provider.suspend_stack(self.stack_name, False)

        # Assert
        self.assertIsInstance(provider_stack, dict)
        self.assertEqual("SUSPEND_IN_PROGRESS", provider_stack["status"])
        self.assertRaises(KeyError, lambda: provider_stack["outputs"])
        heat.actions.suspend.assert_called_with(stack_id=self.stack_name)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_suspend_stack_heat_failure(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.actions.suspend.side_effect = [
            heat_exception
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.suspend_stack(self.stack_name)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_suspend_stack_exception_on_get(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["SUSPEND_IN_PROGRESS"],
            heat_exception
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.suspend_stack(self.stack_name)

    def test_suspend_stack_failure(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["SUSPEND_FAILED"]
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.suspend_stack(self.stack_name)

    def test_delete_stack_wait(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["DELETE_IN_PROGRESS"],
            self.stacks["DELETE_IN_PROGRESS"],
            heat_exc.HTTPNotFound
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider_stack = provider.delete_stack(self.stack_name)

        # Assert
        self.assertIsInstance(provider_stack, dict)
        self.assertEqual("DELETE_COMPLETE", provider_stack["status"])
        self.assertRaises(KeyError, lambda: provider_stack["outputs"])
        heat.stacks.delete.assert_called_with(stack_id=self.stack_name)

    def test_delete_stack_no_wait(self):
        # Setup
        heat = self.get_heat_client_mock()

        # Run
        provider = Provider.init(self.provider_name)
        provider_stack = provider.delete_stack(self.stack_name, False)

        # Assert
        self.assertIsInstance(provider_stack, dict)
        self.assertEqual("DELETE_IN_PROGRESS", provider_stack["status"])
        self.assertRaises(KeyError, lambda: provider_stack["outputs"])
        heat.stacks.delete.assert_called_with(stack_id=self.stack_name)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_delete_stack_exception_on_delete(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.delete.side_effect = [
            heat_exception
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.delete_stack(self.stack_name)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_delete_stack_exception_on_get(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["DELETE_IN_PROGRESS"],
            heat_exception
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.delete_stack(self.stack_name)

    def test_delete_stack_failure(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["DELETE_FAILED"]
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.delete_stack(self.stack_name)


@ddt.ddt
class TestGcloudProvider(TestCase):
    def mock_deployment_service(self):
        return self.mocks["GcloudDeploymentManager"].return_value.get_service.\
            return_value

    def mock_compute_service(self):
        return self.mocks["GcloudComputeEngine"].return_value.get_service.\
            return_value

    def mock_exception(self, status=404, content="exception"):
        resp = Mock()
        resp.status = status
        return gcloud_exc.HttpError(resp, b(content))

    def mock_operation(self, optype, opstate, name="operation", error=False):
        op = {
            "name": name,
            "operationType": optype,
            "status": opstate,
        }

        if error:
            op["error"] = {"errors": [{"message": "error"}]}

        return op

    def mock_deployment(self, optype, opstate, name=None,
                        description=None, manifest_name="manifest"):
        return {
            "name": name and name or self.deployment_name,
            "description": description and description or self.stack_name,
            "operation": self.mock_operation(optype, opstate),
            "manifest": "https://www.googleapis.com/deploymentmanager/v2/projects/project/global/deployments/deployment/manifests/%s" % manifest_name  # noqa: E501
        }

    def mock_resources(self, number, name="server",
                       rtype="compute.v1.instance", zone="zone"):
        resources = []
        for i in range(number):
            properties = {
                "zone": zone
            }
            resource = {
                "type": rtype,
                "name": "%s%d" % (name, i),
                "finalProperties": yaml.dump(properties)
            }
            resources.append(resource)

        return {"resources": resources}

    def mock_manifest(self):
        encoded_key = base64.b64encode(b(self.stack_key))
        layout = {
            "outputs": [
                {"name": "public_ip", "finalValue": self.stack_ip},
                {"name": "private_key", "finalValue": encoded_key},
                {"name": "password", "finalValue": self.stack_password}
            ]
        }
        return {
            "layout": yaml.dump(layout)
        }

    def mock_server(self, status, name="server", zone="zone"):
        return {
            "status": status,
            "name": name,
            "zone": zone
        }

    def setUp(self):
        self.stack_name = "bogus_stack_name"
        self.deployment_name = "s-825a4c28f75f7988620732428c09a19b0adb291e"
        self.stack_user_name = "bogus_stack_user_name"
        self.stack_ip = "127.0.0.1"
        self.stack_key = u"bogus_stack_key"
        self.stack_pubkey = u"bogus_stack_pubkey"
        self.stack_password = "bogus_stack_password"
        self.stack_template = "bogus_stack_template"
        self.stack_environment = yaml.dump({"properties": {}})
        self.protocol = "ssh"
        self.port = None
        self.stack_run = "bogus_run"
        self.course_id = "bogus_course_id"
        self.student_id = "bogus_student_id"
        self.provider_name = "bogus_provider"

        self.provider_conf = {
            "type": "gcloud",
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

        # Mock settings
        self.settings = {
            "sleep_timeout": 0,
            "providers": {
                self.provider_name: self.provider_conf
            }
        }

        # Patchers
        patchers = {
            "GcloudDeploymentManager":
                patch("hastexo.provider.GcloudDeploymentManager"),
            "GcloudComputeEngine":
                patch("hastexo.provider.GcloudComputeEngine"),
            "settings": patch.dict("hastexo.common.DEFAULT_SETTINGS",
                                   self.settings),
        }
        self.mocks = {}
        for mock_name, patcher in patchers.items():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)

    def test_init(self):
        # Run
        provider = Provider.init(self.provider_name)

        # Assert
        self.assertIsInstance(provider, GcloudProvider)
        self.assertNotEqual(provider.ds, None)
        self.assertNotEqual(provider.cs, None)
        self.assertEqual(provider.project, self.provider_conf["gc_project_id"])

    def test_list_existing_stacks(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        deployments = [
            self.mock_deployment(
                "insert",
                "DONE",
                name="s-4c0cf4b0b2efdebeba9bbbd8f42fa14a8d9744e9",
                description="bogus0"
            ),
            self.mock_deployment(
                "insert",
                "DONE",
                name="s-7d98c6ee52aea9d50f29f6b9c450cde65a931d0f",
                description="bogus1"
            ),
            self.mock_deployment(
                "insert",
                "DONE",
                name="s-thisisaninvalidhash",
                description="bogus2"
            ),
            self.mock_deployment(
                "insert",
                "DONE",
                name="not-an-xblock-stack",
                description="bogus3"
            ),
        ]
        response = {"deployments": deployments}
        ds.deployments().list.return_value.execute.return_value = response
        ds.resources().list.return_value.execute.side_effect = [
            self.mock_resources(1),
            self.mock_resources(2)
        ]
        cs.instances().get.return_value.execute.side_effect = [
            self.mock_server("RUNNING"),
            self.mock_server("RUNNING"),
            self.mock_server("RUNNING")
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest(),
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stacks = provider.get_stacks()

        self.assertIsInstance(stacks, list)
        self.assertEqual(len(stacks), 2)
        self.assertEqual("bogus0", stacks[0]["name"])
        self.assertEqual("bogus1", stacks[1]["name"])
        self.assertEqual("CREATE_COMPLETE", stacks[0]["status"])
        self.assertEqual("CREATE_COMPLETE", stacks[1]["status"])

    def test_list_stacks_empty(self):
        # Setup
        ds = self.mock_deployment_service()
        response = {"deployments": []}
        ds.deployments().list.return_value.execute.return_value = response

        # Run
        provider = Provider.init(self.provider_name)
        stacks = provider.get_stacks()

        self.assertIsInstance(stacks, list)
        self.assertEqual(len(stacks), 0)

    def test_list_stacks_not_found(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().list.return_value.execute.side_effect = [
            self.mock_exception(404)
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stacks = provider.get_stacks()

        self.assertIsInstance(stacks, list)
        self.assertEqual(len(stacks), 0)

    def test_list_stacks_exception(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().list.return_value.execute.side_effect = [
            self.mock_exception(500)
        ]

        # Run
        provider = Provider.init(self.provider_name)
        with self.assertRaises(ProviderException):
            provider.get_stacks()

    def test_get_existing_stack(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        deployment = self.mock_deployment("insert", "DONE")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]
        ds.resources().list.return_value.execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get.return_value.execute.side_effect = [
            self.mock_server("RUNNING"),
            self.mock_server("RUNNING")
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.get_stack(self.stack_name)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("CREATE_COMPLETE", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password
        }
        self.assertEqual(stack["outputs"], expected_outputs)

    @ddt.data(
        ("RUNNING", "STOPPING"),
        ("STOPPING", "RUNNING"),
        ("STOPPING", "STOPPING"),
        ("STOPPING", "TERMINATED"),
        ("TERMINATED", "STOPPING"),
        ("STAGING", "STOPPING"),
        ("STOPPING", "STAGING"),
    )
    def test_get_suspending_stack(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        deployment = self.mock_deployment("insert", "DONE")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]
        ds.resources().list.return_value.execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get.return_value.execute.side_effect = [
            self.mock_server(server_states[0]),
            self.mock_server(server_states[1])
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.get_stack(self.stack_name)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("SUSPEND_IN_PROGRESS", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password
        }
        self.assertEqual(stack["outputs"], expected_outputs)

    @ddt.data(
        ("TERMINATED", "STAGING"),
        ("STAGING", "TERMINATED"),
        ("RUNNING", "STAGING"),
        ("STAGING", "RUNNING"),
        ("STAGING", "STAGING"),
    )
    def test_get_resuming_stack(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        deployment = self.mock_deployment("insert", "DONE")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]
        ds.resources().list.return_value.execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get.return_value.execute.side_effect = [
            self.mock_server(server_states[0]),
            self.mock_server(server_states[1])
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.get_stack(self.stack_name)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("RESUME_IN_PROGRESS", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password
        }
        self.assertEqual(stack["outputs"], expected_outputs)

    def test_get_suspended_stack(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        deployment = self.mock_deployment("insert", "DONE")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]
        ds.resources().list.return_value.execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get.return_value.execute.side_effect = [
            self.mock_server("TERMINATED"),
            self.mock_server("TERMINATED")
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.get_stack(self.stack_name)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("SUSPEND_COMPLETE", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password
        }
        self.assertEqual(stack["outputs"], expected_outputs)

    def test_get_unexistent_stack(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().get.return_value.execute.side_effect = [
            self.mock_exception(404)
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.get_stack(self.stack_name)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("DELETE_COMPLETE", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        self.assertFalse(stack["outputs"])

    def test_exception_on_get(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().get.return_value.execute.side_effect = [
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.get_stack(self.stack_name)

    def test_get_with_no_operation(self):
        # Setup
        ds = self.mock_deployment_service()
        deployment = self.mock_deployment("insert", "DONE")
        deployment.pop("operation")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.get_stack(self.stack_name)

    def test_get_with_unknown_operation_type(self):
        # Setup
        ds = self.mock_deployment_service()
        deployment = self.mock_deployment("unknown", "DONE")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.get_stack(self.stack_name)

    def test_get_with_unknown_operation_status(self):
        # Setup
        ds = self.mock_deployment_service()
        deployment = self.mock_deployment("insert", "UNKNOWN")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.get_stack(self.stack_name)

    def test_exception_on_resources_list(self):
        # Setup
        ds = self.mock_deployment_service()
        deployment = self.mock_deployment("insert", "DONE")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]
        ds.resources().list.return_value.execute.side_effect = [
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.get_stack(self.stack_name)

    def test_exception_on_instances_get(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        deployment = self.mock_deployment("insert", "DONE")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]
        ds.resources().list.return_value.execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get.return_value.execute.side_effect = [
            self.mock_server("RUNNING"),
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.get_stack(self.stack_name)

    def test_exception_on_manifests_get(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        deployment = self.mock_deployment("insert", "DONE")
        ds.deployments().get.return_value.execute.side_effect = [
            deployment
        ]
        ds.resources().list.return_value.execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get.return_value.execute.side_effect = [
            self.mock_server("RUNNING"),
            self.mock_server("RUNNING")
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.get_stack(deployment["name"])

    def test_generate_random_password(self):
        provider = Provider.init(self.provider_name)
        password = provider.generate_random_password(64)
        self.assertEqual(len(password), 64)

    def test_generate_key_pair(self):
        provider = Provider.init(self.provider_name)
        pair = provider.generate_key_pair()
        self.assertNotEqual(pair["public_key"], None)
        self.assertNotEqual(pair["private_key"], None)
        self.assertEqual("-----", pair["private_key"][:5])

    def test_generate_b64encoded_key_pair(self):
        provider = Provider.init(self.provider_name)
        pair = provider.generate_key_pair(True)
        self.assertNotEqual(pair["public_key"], None)
        self.assertNotEqual(pair["private_key"], None)
        self.assertNotEqual("-----", pair["private_key"][:5])

    def test_create_stack_success(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.deployments().insert().execute.side_effect = [
            self.mock_deployment("insert", "RUNNING")
        ]
        ds.operations().get().execute.side_effect = [
            self.mock_operation("insert", "RUNNING"),
            self.mock_operation("insert", "DONE"),
        ]
        ds.deployments().get().execute.side_effect = [
            self.mock_deployment("insert", "DONE")
        ]
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server("RUNNING"),
            self.mock_server("RUNNING")
        ]
        ds.manifests().get().execute.side_effect = [
            self.mock_manifest()
        ]
        mock_generate_key_pair = Mock(return_value={
            "public_key": self.stack_pubkey,
            "private_key": self.stack_key
        })
        mock_generate_password = Mock(return_value=self.stack_password)

        # Run
        with patch.multiple('hastexo.provider.Provider',
                            generate_key_pair=mock_generate_key_pair,
                            generate_random_password=mock_generate_password):
            provider = Provider.init(self.provider_name)
            provider.set_template(self.stack_template)
            provider.set_environment(self.stack_environment)
            stack = provider.create_stack(self.stack_name, self.stack_run)

        # Assertions
        self.assertIsInstance(stack, dict)
        self.assertEqual("CREATE_COMPLETE", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password
        }
        self.assertEqual(stack["outputs"], expected_outputs)
        expected_config = {
            "imports": [{"path": "%s.yaml.jinja" % self.deployment_name}],
            "resources": [{
                "type": "%s.yaml.jinja" % self.deployment_name,
                "name": self.deployment_name,
                "properties": {
                    "run": self.stack_run,
                    "private_key": self.stack_key,
                    "public_key": self.stack_pubkey,
                    "password": self.stack_password
                }
            }],
            "outputs": [
                {"name": "public_ip",
                 "value": "$(ref.%s.public_ip)" % self.deployment_name},
                {"name": "private_key",
                 "value": self.stack_key},
                {"name": "password",
                 "value": self.stack_password},
            ]
        }
        expected_body = {
            "target": {
                "imports": [{
                    "name": "%s.yaml.jinja" % self.deployment_name,
                    "content": self.stack_template
                }],
                "config": {
                    "content": yaml.safe_dump(
                        expected_config, default_flow_style=False)
                }
            },
            "name": self.deployment_name,
            "description": self.stack_name
        }
        ds.deployments().insert.assert_called_with(
            project=self.provider_conf["gc_project_id"],
            body=expected_body
        )

    def test_create_stack_exception_with_no_environment(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().insert().execute.side_effect = [
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.create_stack(self.stack_name, "run")

    def test_create_stack_exception_with_empty_environment(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().insert().execute.side_effect = [
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_environment("")
            provider.create_stack(self.stack_name, "run")

    def test_create_stack_exception_with_bogus_environment(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().insert().execute.side_effect = [
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_environment("bogus:::yaml")
            provider.create_stack(self.stack_name, "run")

    def test_create_stack_exception_on_insert(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().insert().execute.side_effect = [
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_template(self.stack_template)
            provider.set_environment(self.stack_environment)
            provider.create_stack(self.stack_name, "run")

    def test_create_stack_exception_on_get(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().insert().execute.side_effect = [
            self.mock_deployment("insert", "RUNNING")
        ]
        ds.operations().get().execute.side_effect = [
            self.mock_operation("insert", "RUNNING"),
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_template(self.stack_template)
            provider.set_environment(self.stack_environment)
            provider.create_stack(self.stack_name, "run")

    def test_create_stack_error_on_done(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().insert().execute.side_effect = [
            self.mock_deployment("insert", "RUNNING")
        ]
        ds.operations().get().execute.side_effect = [
            self.mock_operation("insert", "RUNNING"),
            self.mock_operation("insert", "DONE", error=True),
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.set_template(self.stack_template)
            provider.set_environment(self.stack_environment)
            provider.create_stack(self.stack_name, "run")

    def test_delete_stack_exception(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().delete().execute.side_effect = [
            self.mock_exception(404)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.delete_stack(self.stack_name)

    def test_delete_stack_wait(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().delete().execute.side_effect = [
            self.mock_operation("delete", "RUNNING")
        ]
        ds.operations().get().execute.side_effect = [
            self.mock_operation("delete", "RUNNING"),
            self.mock_operation("delete", "RUNNING"),
            self.mock_operation("delete", "DONE")
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.delete_stack(self.stack_name)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("DELETE_COMPLETE", stack["status"])
        self.assertRaises(KeyError, lambda: stack["outputs"])
        ds.deployments().delete.assert_called_with(
            project=self.provider_conf["gc_project_id"],
            deployment=self.deployment_name)

    def test_delete_stack_wait_with_error(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().delete().execute.side_effect = [
            self.mock_operation("delete", "RUNNING")
        ]
        ds.operations().get().execute.side_effect = [
            self.mock_operation("delete", "RUNNING"),
            self.mock_operation("delete", "RUNNING"),
            self.mock_operation("delete", "DONE", error=True)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.delete_stack(self.deployment_name)

    def test_delete_stack_wait_operation_disappeared(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().delete().execute.side_effect = [
            self.mock_operation("delete", "RUNNING")
        ]
        ds.operations().get().execute.side_effect = [
            self.mock_operation("delete", "RUNNING"),
            self.mock_exception(404)
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.delete_stack(self.stack_name)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("DELETE_COMPLETE", stack["status"])
        self.assertRaises(KeyError, lambda: stack["outputs"])

    def test_delete_stack_no_wait(self):
        # Setup
        ds = self.mock_deployment_service()
        ds.deployments().delete().execute.side_effect = [
            self.mock_operation("delete", "RUNNING")
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.delete_stack(self.stack_name, False)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("DELETE_IN_PROGRESS", stack["status"])
        self.assertRaises(KeyError, lambda: stack["outputs"])
        ds.deployments().delete.assert_called_with(
            project=self.provider_conf["gc_project_id"],
            deployment=self.deployment_name)

    def test_suspend_wait(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2),
            self.mock_resources(2),
            self.mock_resources(2),
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2"),
            self.mock_server("STOPPING", name="server1"),
            self.mock_server("STOPPING", name="server2"),
            self.mock_server("TERMINATED", name="server1"),
            self.mock_server("TERMINATED", name="server2"),
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider_stack = provider.suspend_stack(self.stack_name)

        # Assert
        self.assertIsInstance(provider_stack, dict)
        self.assertEqual("SUSPEND_COMPLETE", provider_stack["status"])
        self.assertRaises(KeyError, lambda: provider_stack["outputs"])
        cs.instances().stop.assert_has_calls([
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server1"),
            call().execute(),
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server2"),
            call().execute(),
        ])

    @ddt.data(
        ("RUNNING", "RUNNING")
    )
    def test_suspend_stack_stops_both_servers(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0], name="server1"),
            self.mock_server(server_states[1], name="server2")
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider_stack = provider.suspend_stack(self.stack_name, False)

        # Assert
        self.assertIsInstance(provider_stack, dict)
        self.assertEqual("SUSPEND_IN_PROGRESS", provider_stack["status"])
        self.assertRaises(KeyError, lambda: provider_stack["outputs"])
        cs.instances().stop.assert_has_calls([
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server1"),
            call().execute(),
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server2"),
            call().execute(),
        ])

    @ddt.data(
        ("RUNNING", "STOPPING"),
        ("RUNNING", "TERMINATED")
    )
    def test_suspend_stack_stops_first_server(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0], name="server1"),
            self.mock_server(server_states[1], name="server2")
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider.suspend_stack(self.stack_name, False)

        # Assert
        cs.instances().stop.assert_has_calls([
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server1"),
            call().execute()
        ])

    @ddt.data(
        ("TERMINATED", "RUNNING"),
        ("STOPPING", "RUNNING")
    )
    def test_suspend_stack_stops_second_server(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0], name="server1"),
            self.mock_server(server_states[1], name="server2")
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider.suspend_stack(self.stack_name, False)

        # Assert
        cs.instances().stop.assert_has_calls([
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server2"),
            call().execute()
        ])

    @ddt.data(
        ("TERMINATED", "TERMINATED"),
        ("TERMINATED", "STOPPING"),
        ("STOPPING", "STOPPING"),
        ("STOPPING", "TERMINATED")
    )
    def test_suspend_stack_stops_no_servers(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0], name="server1"),
            self.mock_server(server_states[1], name="server2")
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider.suspend_stack(self.stack_name, False)

        # Assert
        cs.instances().stop.assert_not_called()

    def test_suspend_stack_exception_on_stop(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server("RUNNING"),
            self.mock_server("RUNNING")
        ]
        cs.instances().stop().execute.side_effect = [
            self.mock_operation("stop", "RUNNING"),
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.suspend_stack(self.stack_name, False)

    def test_suspend_stack_exception_on_get(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2),
            self.mock_resources(2),
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server("RUNNING"),
            self.mock_server("RUNNING"),
            self.mock_server("STOPPING"),
            self.mock_exception(500),
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.suspend_stack(self.stack_name)

    @ddt.data(
        ("RUNNING", "STAGING"),
        ("RUNNING", "PENDING"),
        ("STAGING", "RUNNING"),
        ("STAGING", "STAGING"),
        ("STAGING", "PENDING"),
        ("PENDING", "RUNNING"),
        ("PENDING", "STAGING"),
        ("PENDING", "PENDING")
    )
    def test_suspend_stack_with_wrong_status(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0]),
            self.mock_server(server_states[1])
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.suspend_stack(self.stack_name, False)

    @ddt.data(
        ("TERMINATED", "TERMINATED")
    )
    def test_resume_stack_starts_both_servers(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2),
            self.mock_resources(2),
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0], name="server1"),
            self.mock_server(server_states[1], name="server2"),
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2"),
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2")
        ]
        ds.deployments().get.return_value.execute.side_effect = [
            self.mock_deployment("insert", "DONE")
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.resume_stack(self.stack_name)

        # Assert
        cs.instances().start.assert_has_calls([
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server1"),
            call().execute(),
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server2"),
            call().execute(),
        ])
        self.assertIsInstance(stack, dict)
        self.assertEqual("CREATE_COMPLETE", stack["status"])
        self.assertIsInstance(stack["outputs"], dict)
        expected_outputs = {
            "public_ip": self.stack_ip,
            "private_key": self.stack_key,
            "password": self.stack_password
        }
        self.assertEqual(stack["outputs"], expected_outputs)

    @ddt.data(
        ("TERMINATED", "RUNNING"),
        ("TERMINATED", "STAGING")
    )
    def test_resume_stack_starts_first_server(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2),
            self.mock_resources(2),
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0], name="server1"),
            self.mock_server(server_states[1], name="server2"),
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2"),
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2")
        ]
        ds.deployments().get.return_value.execute.side_effect = [
            self.mock_deployment("insert", "DONE")
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider.resume_stack(self.stack_name)

        # Assert
        cs.instances().start.assert_has_calls([
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server1"),
            call().execute()
        ])

    @ddt.data(
        ("RUNNING", "TERMINATED"),
        ("STAGING", "TERMINATED")
    )
    def test_resume_stack_starts_second_server(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2),
            self.mock_resources(2),
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0], name="server1"),
            self.mock_server(server_states[1], name="server2"),
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2"),
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2")
        ]
        ds.deployments().get.return_value.execute.side_effect = [
            self.mock_deployment("insert", "DONE")
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider.resume_stack(self.stack_name)

        # Assert
        cs.instances().start.assert_has_calls([
            call(project=self.provider_conf["gc_project_id"],
                 zone="zone",
                 instance="server2"),
            call().execute()
        ])

    @ddt.data(
        ("RUNNING", "RUNNING"),
        ("STAGING", "RUNNING"),
        ("RUNNING", "STAGING"),
        ("STAGING", "STAGING")
    )
    def test_resume_stack_starts_no_servers(self, server_states):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2),
            self.mock_resources(2),
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server(server_states[0], name="server1"),
            self.mock_server(server_states[1], name="server2"),
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2"),
            self.mock_server("RUNNING", name="server1"),
            self.mock_server("RUNNING", name="server2")
        ]
        ds.deployments().get.return_value.execute.side_effect = [
            self.mock_deployment("insert", "DONE")
        ]
        ds.manifests().get.return_value.execute.side_effect = [
            self.mock_manifest()
        ]

        # Run
        provider = Provider.init(self.provider_name)
        provider.resume_stack(self.stack_name)

        # Assert
        cs.instances().start.assert_not_called()

    def test_resume_stack_exception_on_start(self):
        # Setup
        ds = self.mock_deployment_service()
        cs = self.mock_compute_service()
        ds.resources().list().execute.side_effect = [
            self.mock_resources(2)
        ]
        cs.instances().get().execute.side_effect = [
            self.mock_server("TERMINATED"),
            self.mock_server("TERMINATED")
        ]
        cs.instances().start().execute.side_effect = [
            self.mock_operation("start", "RUNNING"),
            self.mock_exception(500)
        ]

        # Run
        with self.assertRaises(ProviderException):
            provider = Provider.init(self.provider_name)
            provider.resume_stack(self.stack_name)
