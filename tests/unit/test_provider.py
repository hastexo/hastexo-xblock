import ddt

from unittest import TestCase
from mock import Mock, patch, call
from heatclient import exc as heat_exc
from novaclient import exceptions as nova_exc

from hastexo.provider import (Provider, OpenstackProvider, ProviderException)


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
    heat_exc.HTTPServiceUnavailable
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
                 "output_value": None}
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
            "task_timeouts": {
                "sleep": 0
            },
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
        for mock_name, patcher in patchers.iteritems():
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
            "reboot_on_resume": None
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
            "reboot_on_resume": None
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
            "reboot_on_resume": None
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
            "reboot_on_resume": servers
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

    def test_suspend_stack_success(self):
        # Setup
        heat = self.get_heat_client_mock()

        # Run
        provider = Provider.init(self.provider_name)
        provider.suspend_stack(self.stack_name)

        # Assert
        heat.actions.suspend.assert_called_with(stack_id=self.stack_name)

    @ddt.data(*HEAT_EXCEPTIONS)
    def test_suspend_stack_failure(self, heat_exception):
        # Setup
        heat = self.get_heat_client_mock()
        heat.actions.suspend.side_effect = [
            heat_exception
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
        stack = provider.delete_stack(self.stack_name)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("DELETE_COMPLETE", stack["status"])
        self.assertRaises(KeyError, lambda: stack["outputs"])
        heat.stacks.delete.assert_called_with(stack_id=self.stack_name)

    def test_delete_stack_no_wait(self):
        # Setup
        heat = self.get_heat_client_mock()

        # Run
        provider = Provider.init(self.provider_name)
        stack = provider.delete_stack(self.stack_name, False)

        # Assert
        self.assertIsInstance(stack, dict)
        self.assertEqual("DELETE_IN_PROGRESS", stack["status"])
        self.assertRaises(KeyError, lambda: stack["outputs"])
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
