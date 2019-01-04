import socket

from unittest import TestCase
from mock import Mock, patch

from hastexo.models import Stack
from hastexo.provider import ProviderException
from hastexo.common import get_stack, update_stack, update_stack_fields
from hastexo.tasks import (LaunchStackTask, CheckStudentProgressTask,
                           PING_COMMAND)
from celery.exceptions import SoftTimeLimitExceeded


class TestHastexoTasks(TestCase):
    def get_ssh_client_mock(self):
        return self.mocks["paramiko"].SSHClient.return_value

    def get_socket_mock(self):
        return self.mocks["socket"].socket.return_value

    def get_stack(self, prop=None):
        return get_stack(self.stack_name, self.course_id, self.student_id,
                         prop)

    def update_stack(self, data):
        update_stack(self.stack_name, self.course_id, self.student_id, data)

    def create_stack(self, name, course_id, student_id, data):
        stack, _ = Stack.objects.get_or_create(
            student_id=student_id,
            course_id=course_id,
            name=name)
        update_stack_fields(stack, data)
        stack.save()

    def setUp(self):
        self.stack_name = "bogus_stack_name"
        self.stack_user_name = "bogus_stack_user_name"
        self.stack_ip = "127.0.0.1"
        self.stack_key = u"bogus_stack_key"
        self.stack_password = "bogus_stack_password"
        self.protocol = "ssh"
        self.port = None
        self.stack_run = "bogus_run"
        self.course_id = "bogus_course_id"
        self.student_id = "bogus_student_id"

        # Create a set of mock stacks to be returned by the provider mock.
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
            self.stacks[state] = {
                "status": state,
                "outputs": {
                    "public_ip": self.stack_ip,
                    "private_key": self.stack_key,
                    "password": self.stack_password
                }
            }

        # Mock settings
        self.settings = {
            "task_timeouts": {
                "sleep": 0
            }
        }

        self.providers = [
            {"name": "provider1",
             "capacity": 1,
             "template": "tmpl1",
             "environment": "env1"},
            {"name": "provider2",
             "capacity": 2,
             "template": "tmpl2",
             "environment": "env2"},
            {"name": "provider3",
             "capacity": -1,
             "template": "tmpl3",
             "environment": "env3"}
        ]

        self.kwargs = {
            "providers": self.providers,
            "protocol": self.protocol,
            "port": self.port,
            "stack_run": self.stack_run,
            "stack_name": self.stack_name,
            "stack_user_name": self.stack_user_name,
            "course_id": self.course_id,
            "student_id": self.student_id,
            "reset": False
        }

        # Clear database
        Stack.objects.all().delete()

        # Create stack in the database
        stack, _ = Stack.objects.get_or_create(
            student_id=self.student_id,
            course_id=self.course_id,
            name=self.stack_name,
            protocol=self.protocol,
            port=self.port
        )
        stack.save()

        # Patchers
        patchers = {
            "os": patch("hastexo.tasks.os"),
            "paramiko": patch("hastexo.tasks.paramiko"),
            "socket": patch("hastexo.tasks.socket"),
            "Provider": patch("hastexo.tasks.Provider"),
            "settings": patch.dict("hastexo.common.DEFAULT_SETTINGS",
                                   self.settings),
        }
        self.mocks = {}
        for mock_name, patcher in patchers.items():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)

        self.mocks["os"].system.return_value = 0
        self.mocks["paramiko"].RSAKey.from_private_key.return_value = \
            self.stack_key

        self.mock_providers = []
        for p in self.providers:
            m = Mock()
            m.name = p["name"]
            m.capacity = p["capacity"]
            m.template = p["template"]
            m.environment = p["environment"]
            self.mock_providers.append(m)
        self.mocks["Provider"].init.side_effect = self.mock_providers

    def test_create_stack(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[0]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[0]["name"])
        self.assertNotEqual(res["error_msg"], None)
        provider.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )
        ping_command = PING_COMMAND % (0, self.stack_ip)
        self.mocks["os"].system.assert_called_with(ping_command)
        ssh = self.get_ssh_client_mock()
        ssh.connect.assert_called_with(self.stack_ip,
                                       username=self.stack_user_name,
                                       pkey=self.stack_key)

    def test_provider_error_on_first_provider(self):
        # Setup
        provider1 = self.mock_providers[0]
        provider1.get_stack.side_effect = [
            ProviderException()
        ]
        provider2 = self.mock_providers[1]
        provider2.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider2.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        self.assertEqual(res["error_msg"], "")

    def test_provider_error_on_all_providers(self):
        # Setup
        for m in self.mock_providers:
            m.get_stack.side_effect = [
                ProviderException()
            ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")
        self.assertNotEqual(res["error_msg"], "")

    def test_provider_error_on_create(self):
        # Setup
        provider1 = self.mock_providers[0]
        provider1.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"],
        ]
        provider1.create_stack.side_effect = [
            ProviderException()
        ]
        provider2 = self.mock_providers[1]
        provider2.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"],
        ]
        provider2.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"],
        ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        self.assertEqual(res["error_msg"], "")

    def test_provider_error_on_reset(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [self.stacks["CREATE_FAILED"]]
        provider.delete_stack.side_effect = [ProviderException()]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "CREATE_FAILED"
        })
        self.kwargs["reset"] = True

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")
        self.assertNotEqual(res["error_msg"], "")

    def test_provider_error_on_resume(self):
        # Setup
        provider = self.mock_providers[1]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
            ProviderException()
        ]
        self.update_stack({
            "provider": self.providers[1]["name"],
            "status": "SUSPEND_ISSUED"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "RESUME_FAILED")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        provider.resume_stack.assert_called()

    def test_provider_error_on_cleanup_delete(self):
        # Setup
        provider1 = self.mock_providers[0]
        provider1.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider1.create_stack.side_effect = [
            ProviderException()
        ]
        provider1.delete_stack.side_effect = [
            ProviderException()
        ]
        provider2 = self.mock_providers[1]
        provider2.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"],
        ]
        provider2.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"],
        ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        self.assertEqual(res["error_msg"], "")
        provider1.delete_stack.assert_called()

    def test_provider_error_on_cleanup_resume(self):
        # Setup
        provider = self.mock_providers[1]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
            ProviderException()
        ]
        provider.suspend_stack.side_effect = [
            ProviderException()
        ]
        self.update_stack({
            "provider": self.providers[1]["name"],
            "status": "SUSPEND_ISSUED"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "RESUME_FAILED")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        provider.suspend_stack.assert_called()

    def test_infinite_capacity(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        self.providers[0]["capacity"] = -1
        self.kwargs["providers"] = self.providers
        provider.capacity = -1
        data = {
            "provider": self.providers[0]["name"],
            "status": "CREATE_COMPLETE"
        }
        for i in range(0, 10):
            name = "stack_%d" % i
            student_id = "student_%d" % i
            self.create_stack(name, self.course_id, student_id, data)

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[0]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[0]["name"])
        self.assertEqual(res["error_msg"], "")
        provider.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )

    def test_use_next_provider_if_first_is_disabled(self):
        # Setup
        self.providers[0]["capacity"] = 0
        self.kwargs["providers"] = self.providers
        provider1 = self.mock_providers[0]
        provider1.capacity = 0
        provider2 = self.mock_providers[1]
        provider2.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider2.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        self.assertEqual(res["error_msg"], "")
        provider2.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )

    def test_use_next_provider_if_first_is_full(self):
        # Setup
        capacity = 2
        self.providers[0]["capacity"] = capacity
        self.kwargs["providers"] = self.providers
        provider1 = self.mock_providers[0]
        provider1.capacity = capacity
        provider2 = self.mock_providers[1]
        provider2.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider2.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        data = {
            "provider": self.providers[0]["name"],
            "status": "CREATE_COMPLETE"
        }
        for i in range(0, capacity):
            name = "stack_%d" % i
            student_id = "student_%d" % i
            self.create_stack(name, self.course_id, student_id, data)

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        self.assertEqual(res["error_msg"], "")
        provider2.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )

    def test_all_providers_full(self):
        # Setup
        capacity = 2
        for i, p in enumerate(self.providers):
            p["capacity"] = capacity
            self.mock_providers[i].capacity = capacity
            data = {
                "provider": p["name"],
                "status": "CREATE_COMPLETE"
            }
            for j in range(0, capacity):
                name = "stack_%d_%d" % (i, j)
                student_id = "student_%d_%d" % (i, j)
                self.create_stack(name, self.course_id, student_id, data)
        self.kwargs["providers"] = self.providers

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")
        self.assertEqual(res["provider"], "")
        self.assertEqual(self.get_stack("provider"), "")
        for m in self.mock_providers:
            m.create_stack.assert_not_called()

    def test_use_next_provider_if_create_fails(self):
        # Setup
        provider1 = self.mock_providers[0]
        provider1.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider1.create_stack.side_effect = [
            ProviderException()
        ]
        provider2 = self.mock_providers[1]
        provider2.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider2.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")
        self.assertEqual(res["provider"], self.providers[1]["name"])
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        self.assertNotEqual(res["error_msg"], None)
        provider1.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )
        provider2.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )

    def test_dont_use_next_provider_if_timeout(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            SoftTimeLimitExceeded
        ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")
        self.assertEqual(res["provider"], "")
        self.assertEqual(self.get_stack("provider"), "")

    def test_create_failure_on_all_providers(self):
        # Setup
        for m in self.mock_providers:
            m.get_stack.side_effect = [
                self.stacks["DELETE_COMPLETE"]
            ]
            m.create_stack.side_effect = [
                ProviderException()
            ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")
        self.assertNotEqual(res["error_msg"], "")
        self.assertEqual(res["provider"], "")
        self.assertEqual(self.get_stack("provider"), "")
        for m in self.mock_providers:
            m.create_stack.assert_called_with(
                self.stack_name,
                self.stack_run
            )

    def test_reset_stack(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_FAILED"],
            self.stacks["DELETE_COMPLETE"],
        ]
        provider.delete_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "CREATE_FAILED"
        })
        self.kwargs["reset"] = True

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        provider.delete_stack.assert_called_with(
            self.stack_name
        )
        provider.create_stack.assert_called()
        self.assertEqual(res["status"], "CREATE_COMPLETE")

    def test_dont_reset_new_stack(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        self.kwargs["reset"] = True

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        provider.delete_stack.assert_not_called()
        provider.create_stack.assert_called()
        self.assertEqual(res["status"], "CREATE_COMPLETE")

    def test_resume_suspended_stack(self):
        # Setup
        provider = self.mock_providers[1]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
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
        self.assertEqual(self.get_stack("provider"), self.providers[1]["name"])
        provider.resume_stack.assert_called_with(
            self.stack_name
        )

    def test_resume_suspending_stack(self):
        # Setup
        provider = self.mock_providers[2]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_IN_PROGRESS"],
            self.stacks["SUSPEND_IN_PROGRESS"],
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
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
        self.assertEqual(self.get_stack("provider"), self.providers[2]["name"])
        provider.resume_stack.assert_called_with(
            self.stack_name
        )

    def test_delete_stack_on_create_failed(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            ProviderException()
        ]
        self.providers = [self.providers[0]]
        self.kwargs["providers"] = self.providers

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_FAILED")
        provider.delete_stack.assert_called_with(
            self.stack_name, False
        )

    def test_dont_delete_manually_resumed_stack_on_verify_failure(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        ssh = self.get_ssh_client_mock()
        ssh.connect.side_effect = Exception()
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "RESUME_FAILED")
        provider.delete_stack.assert_not_called()

    def test_eoferror_does_not_constitute_verify_failure(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        ssh = self.get_ssh_client_mock()
        ssh.connect.side_effect = [
            EOFError,
            True
        ]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "CREATE_COMPLETE")

    def test_ssh_bombs_out(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
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
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        system = self.mocks["os"].system
        system.side_effect = SoftTimeLimitExceeded
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        system.assert_called()
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")

    def test_dont_wait_forever_for_ssh(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        ssh = self.get_ssh_client_mock()
        ssh.connect.side_effect = SoftTimeLimitExceeded
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        ssh.connect.assert_called()
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")

    def test_dont_wait_forever_for_rdp(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        s = self.get_socket_mock()
        s.connect.side_effect = [
            socket.timeout,
            socket.timeout,
            socket.timeout,
            SoftTimeLimitExceeded
        ]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })
        self.protocol = "rdp"
        self.kwargs["protocol"] = self.protocol

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        s.connect.assert_called_with((self.stack_ip, 3389))
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")

    def test_dont_wait_forever_for_rdp_on_custom_port(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        s = self.get_socket_mock()
        s.connect.side_effect = [
            socket.timeout,
            socket.timeout,
            socket.timeout,
            SoftTimeLimitExceeded
        ]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "LAUNCH_PENDING"
        })
        self.protocol = "rdp"
        self.port = 3390
        self.kwargs["protocol"] = self.protocol
        self.kwargs["port"] = self.port

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        s.connect.assert_called_with((self.stack_ip, self.port))
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")

    def test_dont_wait_forever_for_suspension(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
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
        provider.delete_stack.assert_not_called()

    def test_cleanup_on_timeout(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            SoftTimeLimitExceeded
        ]

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        provider.delete_stack.assert_called_with(
            self.stack_name, False
        )
        self.assertEqual(res["status"], "LAUNCH_TIMEOUT")

    def test_resume_failed(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
            ProviderException()
        ]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_ISSUED"
        })

        # Run
        res = LaunchStackTask().run(**self.kwargs)

        # Assertions
        self.assertEqual(res["status"], "RESUME_FAILED")

    def test_check_student_progress_failure(self):
        # Setup
        stdout_pass = Mock()
        stdout_pass.channel.recv_exit_status.return_value = 0
        stdout_fail = Mock()
        stdout_fail.channel.recv_exit_status.return_value = 1
        stderr_fail_1 = Mock()
        stderr_fail_1.read = Mock(return_value="single line")
        stderr_fail_2 = Mock()
        stderr_fail_2.read = Mock(return_value="line 1\nline 2")
        stderr_fail_3 = Mock()
        stderr_fail_3.read = Mock(return_value="")
        ssh = self.get_ssh_client_mock()
        ssh.exec_command.side_effect = [
            (None, stdout_pass, None),
            (None, stdout_fail, stderr_fail_1),
            (None, stdout_fail, stderr_fail_2),
            (None, stdout_fail, stderr_fail_3)
        ]
        tests = [
            "test pass",
            "test fail",
            "test fail",
            "test fail"
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
        self.assertEqual(res["pass"], 1)
        self.assertEqual(res["total"], 4)
        self.assertEqual(res["errors"], ["single line", "line 1\nline 2"])

    def test_check_student_progress_success(self):
        # Setup
        stdout_pass = Mock()
        stdout_pass.channel.recv_exit_status.return_value = 0
        ssh = self.get_ssh_client_mock()
        ssh.exec_command.side_effect = [
            (None, stdout_pass, None),
            (None, stdout_pass, None),
            (None, stdout_pass, None)
        ]
        tests = [
            "test pass",
            "test pass",
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
        self.assertEqual(res["pass"], 3)
        self.assertEqual(res["total"], 3)
        self.assertEqual(res["errors"], [])
