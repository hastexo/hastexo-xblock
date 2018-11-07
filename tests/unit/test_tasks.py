from unittest import TestCase
from mock import Mock, patch
from heatclient.exc import HTTPNotFound
from hastexo.models import Stack
from hastexo.utils import update_stack
from hastexo.tasks import (LaunchStackTask, CheckStudentProgressTask,
                           PING_COMMAND)
from celery.exceptions import SoftTimeLimitExceeded


class TestHastexoTasks(TestCase):
    def get_heat_client_mock(self):
        return self.mocks["HeatWrapper"].return_value.get_client.return_value

    def get_ssh_client_mock(self):
        return self.mocks["paramiko"].SSHClient.return_value

    def update_stack(self, data):
        update_stack(self.stack_name, self.course_id, self.student_id, data)

    def setUp(self):
        self.stack_name = "bogus_stack_name"
        self.stack_user_name = "bogus_stack_user_name"
        self.stack_ip = "127.0.0.1"
        self.stack_key = u"bogus_stack_key"
        self.stack_password = "bogus_stack_password"
        self.stack_template = "bogus_stack_template"
        self.stack_protocol = "ssh"
        self.stack_port = 22
        self.stack_run = "bogus_run"
        self.course_id = "bogus_course_id"
        self.student_id = "bogus_student_id"

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

        mock_credentials = {
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
                "provider1": mock_credentials,
                "provider2": mock_credentials,
                "provider3": mock_credentials
            }
        }

        self.providers = [
            {"name": "provider1", "capacity": 1, "environment": "env1"},
            {"name": "provider2", "capacity": 2, "environment": "env2"},
            {"name": "provider3", "capacity": -1, "environment": "env3"}
        ]

        self.kwargs = {
            "providers": self.providers,
            "stack_run": self.stack_run,
            "stack_name": self.stack_name,
            "stack_template": self.stack_template,
            "stack_user_name": self.stack_user_name,
            "course_id": self.course_id,
            "student_id": self.student_id,
            "reset": False
        }

        # Clear database
        Stack.objects.all().delete()

        # Create stack in the database
        self.update_stack({
            "protocol": self.stack_protocol,
            "port": self.stack_port
        })

        # Patchers
        patchers = {
            "os": patch("hastexo.tasks.os"),
            "paramiko": patch("hastexo.tasks.paramiko"),
            "HeatWrapper": patch("hastexo.tasks.HeatWrapper"),
            "NovaWrapper": patch("hastexo.tasks.NovaWrapper"),
            "settings": patch.dict("hastexo.utils.DEFAULT_SETTINGS",
                                   self.settings),
        }
        self.mocks = {}
        for mock_name, patcher in patchers.iteritems():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)

        self.mocks["os"].system.return_value = 0
        self.mocks["paramiko"].RSAKey.from_private_key.return_value = \
            self.stack_key

    def test_create_stack(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_COMPLETE"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[0]["name"])
        self.assertNotEqual(res["error_msg"], None)
        heat.stacks.create.assert_called_with(
            stack_name=self.stack_name,
            template=self.stack_template,
            environment=self.providers[0]["environment"],
            parameters={"run": self.stack_run}
        )
        ping_command = PING_COMMAND % (0, self.stack_ip)
        self.mocks["os"].system.assert_called_with(ping_command)
        ssh = self.get_ssh_client_mock()
        ssh.connect.assert_called_with(self.stack_ip,
                                       username=self.stack_user_name,
                                       pkey=self.stack_key)

    def test_infinite_capacity(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_COMPLETE"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}
        self.providers[0]["capacity"] = -1
        self.kwargs["providers"] = self.providers
        data = {
            "provider": self.providers[0]["name"],
            "status": "CREATE_COMPLETE"
        }
        for i in range(0, 10):
            name = "stack_%d" % i
            student_id = "student_%d" % i
            update_stack(name, self.course_id, student_id, data)

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[0]["name"])
        self.assertEqual(res["error_msg"], "")
        heat.stacks.create.assert_called_with(
            stack_name=self.stack_name,
            template=self.stack_template,
            environment=self.providers[0]["environment"],
            parameters={"run": self.stack_run}
        )

    def test_use_next_provider_if_first_is_disabled(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_COMPLETE"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}
        self.providers[0]["capacity"] = 0
        self.kwargs["providers"] = self.providers

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(res["error_msg"], "")
        heat.stacks.create.assert_called_with(
            stack_name=self.stack_name,
            template=self.stack_template,
            environment=self.providers[1]["environment"],
            parameters={"run": self.stack_run}
        )

    def test_use_next_provider_if_first_is_full(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_COMPLETE"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}
        capacity = 2
        self.providers[0]["capacity"] = capacity
        self.kwargs["providers"] = self.providers
        data = {
            "provider": self.providers[0]["name"],
            "status": "CREATE_COMPLETE"
        }
        for i in range(0, capacity):
            name = "stack_%d" % i
            student_id = "student_%d" % i
            update_stack(name, self.course_id, student_id, data)

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(res["error_msg"], "")
        heat.stacks.create.assert_called_with(
            stack_name=self.stack_name,
            template=self.stack_template,
            environment=self.providers[1]["environment"],
            parameters={"run": self.stack_run}
        )

    def test_all_providers_full(self):
        # Setup
        capacity = 2
        for i, p in enumerate(self.providers):
            p["capacity"] = capacity
            data = {
                "provider": p["name"],
                "status": "CREATE_COMPLETE"
            }
            for j in range(0, capacity):
                name = "stack_%d_%d" % (i, j)
                student_id = "student_%d_%d" % (i, j)
                update_stack(name, self.course_id, student_id, data)
        self.kwargs["providers"] = self.providers

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")
        self.assertEqual(res["provider"], "")
        heat = self.get_heat_client_mock()
        heat.stacks.create.assert_not_called()

    def test_use_next_provider_if_create_fails(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_FAILED"],
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_COMPLETE"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertNotEqual(res["error_msg"], None)
        heat.stacks.create.assert_called_with(
            stack_name=self.stack_name,
            template=self.stack_template,
            environment=self.providers[1]["environment"],
            parameters={"run": self.stack_run}
        )

    def test_dont_use_next_provider_if_timeout(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_IN_PROGRESS"],
            SoftTimeLimitExceeded
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")
        self.assertEqual(res["provider"], "")

    def test_create_failure_on_all_providers(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_FAILED"],
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_FAILED"],
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_FAILED"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")
        self.assertNotEqual(res["error_msg"], "")
        self.assertEqual(res["provider"], "")
        heat.stacks.create.assert_called_with(
            stack_name=self.stack_name,
            template=self.stack_template,
            environment=self.providers[2]["environment"],
            parameters={"run": self.stack_run}
        )

    def test_reset_stack(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["CREATE_FAILED"],
            self.stacks["DELETE_IN_PROGRESS"],
            HTTPNotFound,
            self.stacks["DELETE_COMPLETE"],
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_COMPLETE"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "CREATE_FAILED"
        })
        self.kwargs["reset"] = True

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        heat.stacks.delete.assert_called_with(
            stack_id=self.stacks["CREATE_FAILED"].id
        )
        heat.stacks.create.assert_called()
        self.assertEqual(res["status"], "CREATE_COMPLETE")

    def test_dont_reset_new_stack(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_COMPLETE"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}
        self.kwargs["reset"] = True

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        heat.stacks.delete.assert_not_called()
        heat.stacks.create.assert_called()
        self.assertEqual(res["status"], "CREATE_COMPLETE")

    def test_resume_suspended_stack(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["SUSPEND_COMPLETE"],
            self.stacks["RESUME_IN_PROGRESS"],
            self.stacks["RESUME_IN_PROGRESS"],
            self.stacks["RESUME_COMPLETE"]
        ]
        self.update_stack({
            "provider": self.providers[1]["name"],
            "status": "SUSPEND_ISSUED"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "RESUME_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        heat.actions.resume.assert_called_with(
            stack_id=self.stacks["SUSPEND_COMPLETE"].id
        )

    def test_resume_suspending_stack(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["SUSPEND_IN_PROGRESS"],
            self.stacks["SUSPEND_IN_PROGRESS"],
            self.stacks["SUSPEND_COMPLETE"],
            self.stacks["RESUME_IN_PROGRESS"],
            self.stacks["RESUME_IN_PROGRESS"],
            self.stacks["RESUME_COMPLETE"]
        ]
        self.update_stack({
            "provider": self.providers[2]["name"],
            "status": "SUSPEND_ISSUED"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "RESUME_COMPLETE")
        self.assertEqual(res["provider"], self.providers[2]["name"])
        heat.actions.resume.assert_called_with(
            stack_id=self.stacks["SUSPEND_COMPLETE"].id
        )

    def test_delete_stack_on_create_failed(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_FAILED"]
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}
        self.providers = [self.providers[0]]
        self.kwargs["providers"] = self.providers

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")
        heat.stacks.delete.assert_called_with(
            stack_id=self.stack_name
        )

    def test_ssh_bombs_out(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.return_value = self.stacks["CREATE_COMPLETE"]
        ssh = self.get_ssh_client_mock()
        ssh.connect.side_effect = Exception()
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")

    def test_dont_wait_forever_for_ping(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.return_value = self.stacks["CREATE_COMPLETE"]
        system = self.mocks["os"].system
        system.side_effect = SoftTimeLimitExceeded
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")

    def test_dont_wait_forever_for_ssh(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.return_value = self.stacks["CREATE_COMPLETE"]
        ssh = self.get_ssh_client_mock()
        ssh.connect.side_effect = SoftTimeLimitExceeded
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")

    def test_dont_wait_forever_for_suspension(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["SUSPEND_IN_PROGRESS"],
            self.stacks["SUSPEND_IN_PROGRESS"],
            SoftTimeLimitExceeded
        ]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_ISSUED"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")
        heat.stacks.delete.assert_not_called()

    def test_cleanup_on_timeout(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks["CREATE_IN_PROGRESS"],
            self.stacks["CREATE_IN_PROGRESS"],
            SoftTimeLimitExceeded
        ]
        heat.stacks.create.return_value = {"stack": {"id": self.stack_name}}

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        heat.stacks.delete.assert_called_with(
            stack_id=self.stack_name
        )
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")

    def test_resume_failed(self):
        # Setup
        heat = self.get_heat_client_mock()
        heat.stacks.get.side_effect = [
            self.stacks["SUSPEND_COMPLETE"],
            self.stacks["RESUME_IN_PROGRESS"],
            self.stacks["RESUME_IN_PROGRESS"],
            self.stacks["RESUME_FAILED"]
        ]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_ISSUED"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "RESUME_FAILED")

    def test_check_student_progress(self):
        # Setup
        stdout_pass = Mock()
        stdout_pass.channel.recv_exit_status.return_value = 0
        stdout_fail = Mock()
        stdout_fail.channel.recv_exit_status.return_value = 1
        ssh = self.get_ssh_client_mock()
        ssh.exec_command.side_effect = [
            (None, stdout_pass, None),
            (None, stdout_fail, None),
            (None, stdout_pass, None)
        ]
        tests = [
            "test pass",
            "test fail",
            "test pass"
        ]
        kwargs = {
            "tests": tests,
            "stack_ip": self.stack_ip,
            "stack_key": self.stack_key,
            "stack_user_name": self.stack_user_name
        }

        # Run
        res = CheckStudentProgressTask().run(**kwargs)

        # Assertions
        self.assertEqual(res["status"], "CHECK_PROGRESS_COMPLETE")
        self.assertEqual(res["pass"], 2)
        self.assertEqual(res["total"], 3)
