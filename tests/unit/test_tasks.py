import copy
import socket

from unittest import TestCase
from mock import Mock, patch

from hastexo.models import Stack
from hastexo.provider import ProviderException
from hastexo.common import (
    get_stack,
    update_stack,
    update_stack_fields,
    RemoteExecException,
)
from hastexo.tasks import (
    PING_COMMAND,
    LaunchStackTask,
    SuspendStackTask,
    DeleteStackTask,
    CheckStudentProgressTask,
)
from celery.exceptions import SoftTimeLimitExceeded
from django.db.utils import OperationalError


class HastexoTestCase(TestCase):
    STACK_IP = "127.0.0.1"
    PING_BINARY = 'ping'

    def setUp(self):
        self.stack_name = "bogus_stack_name"
        self.stack_user_name = "bogus_stack_user_name"
        self.stack_key = u"bogus_stack_key"
        self.stack_password = "bogus_stack_password"
        self.protocol = "ssh"
        self.port = None
        self.stack_run = "bogus_run"
        self.course_id = "bogus_course_id"
        self.student_id = "bogus_student_id"
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
        self.hook_script = "bogus_hook_script"
        self.hook_events = {
            "suspend": True,
            "resume": True,
            "delete": True
        }
        self.read_from_contentstore = "bogus_content"

        # Mock settings
        self.settings = {
            "sleep_timeout": 0,
            "delete_attempts": 2,
        }

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
                    "public_ip": self.STACK_IP,
                    "private_key": self.stack_key,
                    "password": self.stack_password
                }
            }

        # Clear database
        Stack.objects.all().delete()

        # Create stack in the database
        stack, _ = Stack.objects.get_or_create(
            student_id=self.student_id,
            course_id=self.course_id,
            name=self.stack_name,
            status="LAUNCH_PENDING",
            protocol=self.protocol,
            port=self.port,
            run=self.stack_run,
            user=self.stack_user_name,
            providers=self.providers,
            hook_script=self.hook_script,
            hook_events=self.hook_events,
            delete_age=1209600  # default settings value of 14 days in seconds
        )
        stack.save()

        # Run kwargs
        self.kwargs = {
            "stack_id": stack.id,
            "reset": False
        }

        # Patchers
        patchers = {
            "os": patch("hastexo.tasks.os"),
            "socket": patch("hastexo.tasks.socket"),
            "Provider": patch("hastexo.tasks.Provider"),
            "settings": patch.dict("hastexo.common.DEFAULT_SETTINGS",
                                   self.settings),
            "ssh_to": patch("hastexo.tasks.ssh_to"),
            "read_from_contentstore": patch(
                "hastexo.tasks.read_from_contentstore"),
            "remote_exec": patch("hastexo.tasks.remote_exec"),
        }
        self.mocks = {}
        for mock_name, patcher in patchers.items():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)

        self.mocks["os"].system.return_value = 0
        self.mocks["read_from_contentstore"].return_value = \
            self.read_from_contentstore
        self.mocks["remote_exec"].return_value = 0

        # Set up mock providers
        self.mock_providers = []
        for p in self.providers:
            m = Mock()
            m.name = p["name"]
            m.capacity = p["capacity"]
            m.template = p["template"]
            m.environment = p["environment"]
            self.mock_providers.append(m)
        self.mocks["Provider"].init.side_effect = self.mock_providers

    def get_ssh_to_mock(self):
        return self.mocks["ssh_to"]

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


class TestLaunchStackTask(HastexoTestCase):
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[0]["name"])
        self.assertEqual(stack.error_msg, u"")
        provider.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )
        ping_command = PING_COMMAND % (self.PING_BINARY,
                                       0,
                                       self.STACK_IP)
        self.mocks["os"].system.assert_called_with(ping_command)
        self.mocks["ssh_to"].assert_called_with(
            self.stack_user_name,
            self.STACK_IP,
            self.stack_key
        )
        self.assertFalse(self.mocks["remote_exec"].called)

    def test_create_stack_transient_database_error(self):
        """
        Try to launch a new stack, but simulate a database error, only
        on the first two calls. Such an error
        should cause the stack count to be retried. When the error
        does not persist on the third try, the task should succeed.
        """

        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]

        # Mock OperationalError 2 times with Stack.objects.filter()
        with patch("hastexo.models.Stack.objects.filter") as filter_patch:
            filter_patch.side_effect = [OperationalError,
                                        OperationalError,
                                        Stack.objects]
            # Run
            LaunchStackTask().run(**self.kwargs)

        # The filter() method would have to be called 3 times
        # (2 failures with an OperationalError, then 1 success).
        self.assertEqual(filter_patch.call_count, 3)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[0]["name"])
        self.assertEqual(stack.error_msg, u"")
        provider.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )
        ping_command = PING_COMMAND % (self.PING_BINARY,
                                       0,
                                       self.STACK_IP)
        self.mocks["os"].system.assert_called_with(ping_command)
        self.mocks["ssh_to"].assert_called_with(
            self.stack_user_name,
            self.STACK_IP,
            self.stack_key
        )
        self.assertFalse(self.mocks["remote_exec"].called)

    def test_create_stack_persistent_database_error(self):
        """
        Try to launch a new stack, but simulate a persistent database
        error in the process. Such an error should cause the task to
        fail.
        """

        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            self.stacks["CREATE_FAILED"]
        ]

        # Mock OperationalError 3 times with Stack.objects.filter()
        with patch("hastexo.models.Stack.objects.filter") as filter_patch:
            filter_patch.side_effect = [OperationalError,
                                        OperationalError,
                                        OperationalError]
            # Run
            with self.assertRaises(OperationalError):
                LaunchStackTask().run(**self.kwargs)

            # The filter() method would have to be called 3 times.
            self.assertEqual(filter_patch.call_count, 3)

    def test_create_stack_has_no_ip(self):
        # Setup
        provider1 = self.mock_providers[0]
        provider1.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        create_complete_stack = copy.deepcopy(self.stacks["CREATE_COMPLETE"])
        create_complete_stack["outputs"]["public_ip"] = None
        provider1.create_stack.side_effect = [
            create_complete_stack
        ]
        provider2 = self.mock_providers[1]
        provider2.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider2.create_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        provider1.delete_stack.assert_called()

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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertEqual(stack.error_msg, u"")

    def test_provider_error_on_all_providers(self):
        # Setup
        for m in self.mock_providers:
            m.get_stack.side_effect = [
                ProviderException()
            ]

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_FAILED")
        self.assertNotEqual(stack.error_msg, u"")

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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertEqual(stack.error_msg, u"")

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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_FAILED")
        self.assertNotEqual(stack.error_msg, u"")

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
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_FAILED")
        self.assertEqual(stack.provider, self.providers[1]["name"])
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertEqual(stack.error_msg, u"")
        provider1.delete_stack.assert_called()

    def test_timeout_on_cleanup_delete(self):
        # Setup
        provider1 = self.mock_providers[0]
        provider1.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider1.create_stack.side_effect = [
            ProviderException()
        ]
        provider1.delete_stack.side_effect = [
            SoftTimeLimitExceeded()
        ]

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")
        self.assertEqual(stack.provider, "")
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
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_FAILED")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        provider.suspend_stack.assert_called()

    def test_undefined_capacity(self):
        # Setup
        self.providers[0].pop("capacity")
        self.update_stack({"providers": self.providers})

        # Assert LaunchStackTask() fails if capacity is not defined
        # for a provider.
        with self.assertRaises(KeyError):
            LaunchStackTask().run(**self.kwargs)

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
        self.update_stack({"providers": self.providers})
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[0]["name"])
        self.assertEqual(stack.error_msg, u"")
        provider.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )

    def test_use_next_provider_if_first_is_disabled(self):
        # Setup
        self.providers[0]["capacity"] = 0
        self.update_stack({"providers": self.providers})
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertEqual(stack.error_msg, u"")
        provider2.create_stack.assert_called_with(
            self.stack_name,
            self.stack_run
        )

    def test_use_next_provider_if_first_is_full(self):
        # Setup
        capacity = 2
        self.providers[0]["capacity"] = capacity
        self.update_stack({"providers": self.providers})
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertEqual(stack.error_msg, u"")
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
            # A suspended stack counts toward the provider capacity,
            # just like a freshly created one does.
            data = {
                "provider": p["name"],
                "status": "SUSPEND_COMPLETE"
            }
            for j in range(0, capacity):
                name = "stack_%d_%d" % (i, j)
                student_id = "student_%d_%d" % (i, j)
                self.create_stack(name, self.course_id, student_id, data)
        self.update_stack({"providers": self.providers})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_FAILED")
        self.assertEqual(stack.provider, "")
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertEqual(stack.error_msg, u"")
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")
        self.assertEqual(stack.provider, "")

    def test_timeout_on_get_stack(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            SoftTimeLimitExceeded
        ]

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")
        self.assertEqual(stack.provider, "")

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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_FAILED")
        self.assertNotEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        provider.delete_stack.assert_called_with(
            self.stack_name
        )
        provider.create_stack.assert_called()
        self.assertEqual(stack.status, "CREATE_COMPLETE")

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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        provider.delete_stack.assert_not_called()
        provider.create_stack.assert_called()
        self.assertEqual(stack.status, "CREATE_COMPLETE")

    def test_reset_timeout_on_delete(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_FAILED"],
        ]
        provider.delete_stack.side_effect = [
            SoftTimeLimitExceeded
        ]
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "CREATE_FAILED"
        })
        self.kwargs["reset"] = True

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")
        self.assertEqual(stack.provider, "")

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
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.mocks["remote_exec"].assert_called_with(
            self.mocks["ssh_to"].return_value,
            self.read_from_contentstore,
            params="resume"
        )

    def test_resume_suspended_stack_transient_operational_error(self):
        """
        Try to resume a previously suspended stack, but simulate a
        database error, but only on the first two calls. Such an error
        should cause the stack update to be retried. When the error
        does not persist on the third try, the task should succeed.
        """

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
            "status": "SUSPEND_COMPLETE"
        })

        # Mock OperationalError 2 times
        with patch.object(Stack, 'save', side_effect=[OperationalError,
                                                      OperationalError,
                                                      None]) as save_patch:
            # Run
            LaunchStackTask().run(**self.kwargs)

            # The save() method would have to be called 3 times (2
            # failures with an OperationalError, then 1 success).
            self.assertEqual(save_patch.call_count, 3)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        # self.assertEqual(stack.status, "RESUME_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])

    def test_resume_suspended_stack_persistent_operational_error(self):
        """
        Try to resume a previously suspended stack, but simulate a
        persistent database error in the process. Such an error should cause
        the task to fail.
        """

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
            "status": "SUSPEND_COMPLETE"
        })

        # Mock OperationalError 3 times
        with patch.object(
            Stack, 'save', side_effect=[OperationalError,
                                        OperationalError,
                                        OperationalError]) as save_patch:
            # Run
            with self.assertRaises(OperationalError):
                LaunchStackTask().run(**self.kwargs)

            # The save() method would have to be called 3 times.
            self.assertEqual(save_patch.call_count, 3)

        # Fetch stack
        stack = self.get_stack()

        # Assertions

        # Whatever happened in the database could have caused the
        # stack status to be anything *except* successful resume.
        self.assertNotEqual(stack.status, "RESUME_COMPLETE")

        # Regardless, the database information about the stack
        # provider should still be unchanged.
        self.assertEqual(stack.provider, self.providers[1]["name"])

    def test_resumed_stack_has_no_ip(self):
        # Setup
        provider = self.mock_providers[1]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        resume_complete_stack = copy.deepcopy(self.stacks["RESUME_COMPLETE"])
        resume_complete_stack["outputs"]["public_ip"] = None
        provider.resume_stack.side_effect = [
            resume_complete_stack
        ]
        self.update_stack({
            "provider": self.providers[1]["name"],
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_FAILED")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        provider.suspend_stack.assert_called()

    def test_timeout_resuming_stack(self):
        # Setup
        provider = self.mock_providers[1]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
            SoftTimeLimitExceeded
        ]
        self.update_stack({
            "provider": self.providers[1]["name"],
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")
        self.assertEqual(stack.provider, self.providers[1]["name"])

    def test_resume_hook_empty(self):
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
            "status": "SUSPEND_COMPLETE",
            "hook_events": {},
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertFalse(self.mocks["remote_exec"].called)

    def test_resume_hook_exception(self):
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
            "status": "SUSPEND_COMPLETE"
        })
        self.mocks["remote_exec"].side_effect = Exception()

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertTrue(self.mocks["remote_exec"].called)

    def test_resume_hook_failure(self):
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
            "status": "SUSPEND_COMPLETE"
        })
        self.mocks["remote_exec"].side_effect = RemoteExecException

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_COMPLETE")
        self.assertEqual(stack.provider, self.providers[1]["name"])
        self.assertTrue(self.mocks["remote_exec"].called)

    def test_error_waiting_for_stack_to_change_state_on_resume(self):
        # Setup
        provider = self.mock_providers[2]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_IN_PROGRESS"],
            ProviderException()
        ]
        self.update_stack({
            "provider": self.providers[2]["name"],
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_FAILED")
        self.assertEqual(stack.provider, self.providers[2]["name"])

    def test_error_waiting_for_stack_to_change_state_on_create(self):
        # Setup
        provider = self.mock_providers[2]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_IN_PROGRESS"],
            ProviderException()
        ]
        self.update_stack({
            "provider": self.providers[2]["name"],
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_FAILED")
        self.assertEqual(stack.provider, "")

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
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_COMPLETE")
        self.assertEqual(stack.provider, self.providers[2]["name"])
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
        self.update_stack({"providers": self.providers})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_FAILED")
        provider.delete_stack.assert_called_with(
            self.stack_name, False
        )

    def test_cleanup_timeout_on_create_failed(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]
        provider.create_stack.side_effect = [
            ProviderException()
        ]
        self.providers = [self.providers[0]]
        self.update_stack({"providers": self.providers})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_FAILED")
        provider.delete_stack.assert_called_with(
            self.stack_name, False
        )

    def test_dont_delete_manually_resumed_stack_on_verify_failure(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        self.mocks["ssh_to"].side_effect = Exception()
        self.update_stack({"provider": self.providers[0]["name"]})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_FAILED")
        provider.delete_stack.assert_not_called()

    def test_eoferror_does_not_constitute_verify_failure(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        ssh = self.mocks["ssh_to"]
        ssh.connect.side_effect = [
            EOFError,
            True
        ]
        self.update_stack({"provider": self.providers[0]["name"]})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_COMPLETE")

    def test_ssh_bombs_out(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        self.mocks["ssh_to"].side_effect = Exception()
        self.update_stack({"provider": self.providers[0]["name"]})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "CREATE_FAILED")

    def test_dont_wait_forever_for_ping(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        system = self.mocks["os"].system
        system.side_effect = SoftTimeLimitExceeded
        self.update_stack({"provider": self.providers[0]["name"]})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        system.assert_called()
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")

    def test_dont_wait_forever_for_ssh(self):
        # Setup
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        self.mocks["ssh_to"].side_effect = SoftTimeLimitExceeded
        self.update_stack({"provider": self.providers[0]["name"]})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertTrue(self.mocks["ssh_to"].called)
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")

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
        self.update_stack({"provider": self.providers[0]["name"]})
        self.protocol = "rdp"
        self.update_stack({"protocol": self.protocol})

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        s.connect.assert_called_with((self.STACK_IP, 3389))
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")

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
        self.protocol = "rdp"
        self.port = 3390
        self.update_stack({
            "provider": self.providers[0]["name"],
            "protocol": self.protocol,
            "port": self.port,
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        s.connect.assert_called_with((self.STACK_IP, self.port))
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")

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
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")
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
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        provider.delete_stack.assert_called_with(
            self.stack_name, False
        )
        self.assertEqual(stack.status, "LAUNCH_TIMEOUT")

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
            "status": "SUSPEND_COMPLETE"
        })

        # Run
        LaunchStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_FAILED")


class TestSuspendStackTask(HastexoTestCase):
    def test_suspend_up_stack(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        provider.suspend_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "SUSPEND_COMPLETE")
        self.assertIsNotNone(stack.delete_by)
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, self.providers[0]["name"])
        self.mocks["remote_exec"].assert_called_with(
            self.mocks["ssh_to"].return_value,
            self.read_from_contentstore,
            params="suspend"
        )

    def test_suspend_suspend_failed_stack(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_FAILED"]
        ]
        provider.suspend_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "SUSPEND_COMPLETE")
        self.assertIsNotNone(stack.delete_by)
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, self.providers[0]["name"])
        self.mocks["remote_exec"].assert_called_with(
            self.mocks["ssh_to"].return_value,
            self.read_from_contentstore,
            params="suspend"
        )

    def test_suspend_hook_empty(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING",
            "hook_events": {},
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        provider.suspend_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "SUSPEND_COMPLETE")
        self.assertIsNotNone(stack.delete_by)
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, self.providers[0]["name"])
        self.mocks["remote_exec"].assert_not_called()

    def test_suspend_even_if_hook_fails(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        self.mocks["remote_exec"].side_effect = [
            RemoteExecException("error message")
        ]
        provider.suspend_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "SUSPEND_COMPLETE")
        self.assertIsNotNone(stack.delete_by)
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, self.providers[0]["name"])
        self.mocks["remote_exec"].assert_called_with(
            self.mocks["ssh_to"].return_value,
            self.read_from_contentstore,
            params="suspend"
        )

    def test_suspend_even_if_hook_exception(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        self.mocks["remote_exec"].side_effect = Exception("")
        provider.suspend_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "SUSPEND_COMPLETE")
        self.assertIsNotNone(stack.delete_by)
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, self.providers[0]["name"])
        self.mocks["remote_exec"].assert_called_with(
            self.mocks["ssh_to"].return_value,
            self.read_from_contentstore,
            params="suspend"
        )

    def test_dont_suspend_deleted_stack(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        provider.suspend_stack.assert_not_called()
        self.mocks["remote_exec"].assert_not_called()

    def test_dont_suspend_failed_stack(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_FAILED"]
        ]

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "RESUME_FAILED")
        self.assertEqual(stack.error_msg, u"")
        provider.suspend_stack.assert_not_called()
        self.mocks["remote_exec"].assert_not_called()

    def test_mark_failed_on_exception(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = Exception()

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "SUSPEND_FAILED")
        self.assertIsNotNone(stack.delete_by)
        self.assertNotEqual(stack.error_msg, u"")

    def dont_wait_for_suspension_forever(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "SUSPEND_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        provider.suspend_stack.side_effect = SoftTimeLimitExceeded

        # Run
        SuspendStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "SUSPEND_FAILED")
        self.assertIsNotNone(stack.delete_by)
        self.assertNotEqual(stack.error_msg, u"")


class TestDeleteStackTask(HastexoTestCase):
    def test_delete_suspended_stack(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        provider.delete_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")
        provider.resume_stack.assert_called()
        self.mocks["remote_exec"].assert_called_with(
            self.mocks["ssh_to"].return_value,
            self.read_from_contentstore,
            params="delete"
        )
        provider.delete_stack.assert_called()

    def test_delete_up_stack(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["CREATE_COMPLETE"]
        ]
        provider.delete_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")
        provider.resume_stack.assert_not_called()
        provider.delete_stack.assert_called()
        self.mocks["remote_exec"].assert_called_with(
            self.mocks["ssh_to"].return_value,
            self.read_from_contentstore,
            params="delete"
        )

    def test_delete_failed_stack(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["DELETE_FAILED"]
        ]
        provider.delete_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")
        provider.resume_stack.assert_not_called()
        self.mocks["remote_exec"].assert_not_called()
        provider.delete_stack.assert_called()

    def test_delete_suspended_stack_even_if_resume_fails(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = Exception()
        provider.delete_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")
        provider.resume_stack.assert_called()
        provider.delete_stack.assert_called()
        self.mocks["remote_exec"].assert_not_called()

    def test_delete_hook_empty(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING",
            "hook_events": {},
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.delete_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")
        provider.resume_stack.assert_not_called()
        self.mocks["remote_exec"].assert_not_called()
        provider.delete_stack.assert_called()

    def test_delete_suspended_stack_even_if_hook_fails(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        self.mocks["remote_exec"].side_effect = [
            RemoteExecException("error message")
        ]
        provider.delete_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")
        provider.resume_stack.assert_called()
        self.mocks["remote_exec"].assert_called()
        provider.delete_stack.assert_called()

    def test_delete_suspended_stack_even_if_hook_exception(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"]
        ]
        provider.resume_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"]
        ]
        self.mocks["remote_exec"].side_effect = Exception("")
        provider.delete_stack.side_effect = [
            self.stacks["DELETE_COMPLETE"]
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")
        provider.resume_stack.assert_called()
        self.mocks["remote_exec"].assert_called()
        provider.delete_stack.assert_called()

    def test_retry_on_exception(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"],
            self.stacks["SUSPEND_COMPLETE"],
        ]
        provider.resume_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"],
            self.stacks["RESUME_COMPLETE"],
        ]
        provider.delete_stack.side_effect = [
            Exception(""),
            self.stacks["DELETE_COMPLETE"],
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_COMPLETE")
        self.assertEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, u"")

    def test_mark_failed_after_attempts(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"],
            self.stacks["SUSPEND_COMPLETE"],
        ]
        provider.resume_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"],
            self.stacks["RESUME_COMPLETE"],
        ]
        provider.delete_stack.side_effect = [
            Exception(""),
            Exception(""),
        ]

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_FAILED")
        self.assertNotEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, self.providers[0]["name"])

    def test_dont_wait_forever_for_deletion(self):
        # Setup
        self.update_stack({
            "provider": self.providers[0]["name"],
            "status": "DELETE_PENDING"
        })
        provider = self.mock_providers[0]
        provider.get_stack.side_effect = [
            self.stacks["SUSPEND_COMPLETE"],
        ]
        provider.resume_stack.side_effect = [
            self.stacks["RESUME_COMPLETE"],
        ]
        provider.delete_stack.side_effect = SoftTimeLimitExceeded

        # Run
        DeleteStackTask().run(**self.kwargs)

        # Fetch stack
        stack = self.get_stack()

        # Assertions
        self.assertEqual(stack.status, "DELETE_FAILED")
        self.assertNotEqual(stack.error_msg, u"")
        self.assertEqual(stack.provider, self.providers[0]["name"])


class TestCheckStudentProgressTask(HastexoTestCase):
    def test_check_student_progress_failure(self):
        # Setup
        stderr_fail_1 = "single line"
        stderr_fail_2 = "line 1\nline 2"
        stderr_fail_3 = ""
        self.mocks["remote_exec"].side_effect = [
            0,
            RemoteExecException(stderr_fail_1),
            RemoteExecException(stderr_fail_2),
            RemoteExecException(stderr_fail_3),
        ]
        tests = [
            "test pass",
            "test fail",
            "test fail",
            "test fail"
        ]
        kwargs = {
            "tests": tests,
            "stack_ip": self.STACK_IP,
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
        self.mocks["remote_exec"].return_value = 0
        tests = [
            "test pass",
            "test pass",
            "test pass"
        ]
        kwargs = {
            "tests": tests,
            "stack_ip": self.STACK_IP,
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

    def test_check_student_progress_hints(self):
        # Setup
        # Double error messages as bytes and strings,
        # to test if both will be handeled accordingly
        stderr_fail_1 = b'single line'
        stderr_fail_2 = "single line"
        stderr_fail_3 = b'line 1\nline 2'
        stderr_fail_4 = "line 1\nline 2"
        stderr_fail_5 = b''
        stderr_fail_6 = ""

        self.mocks["remote_exec"].side_effect = [
            0,
            RemoteExecException(stderr_fail_1),
            RemoteExecException(stderr_fail_2),
            RemoteExecException(stderr_fail_3),
            RemoteExecException(stderr_fail_4),
            RemoteExecException(stderr_fail_5),
            RemoteExecException(stderr_fail_6),
        ]
        tests = [
            "test pass",
            "test fail",
            "test fail",
            "test fail",
            "test fail",
            "test fail",
            "test fail"
        ]
        kwargs = {
            "tests": tests,
            "stack_ip": self.STACK_IP,
            "stack_key": self.stack_key,
            "stack_user_name": self.stack_user_name
        }

        # Run
        res = CheckStudentProgressTask().run(**kwargs)

        # Assertions
        self.assertEqual(res["status"], "CHECK_PROGRESS_COMPLETE")
        self.assertEqual(res["pass"], 1)
        self.assertEqual(res["total"], 7)

        # Assert that all errors are displayed as strings,
        # stderr_fail 5 and 6 are read as empty and not displayed
        self.assertEqual(res["errors"], [
            "single line",
            "single line",
            "line 1\nline 2",
            "line 1\nline 2"
        ])


class HastexoIPv6TestCase(HastexoTestCase):
    STACK_IP = "::1"
    PING_BINARY = 'ping6'


class TestLaunchStackTaskIPv6(TestLaunchStackTask,
                              HastexoIPv6TestCase):
    pass


class TestSuspendStackTaskIPv6(TestSuspendStackTask,
                               HastexoIPv6TestCase):
    pass


class TestDeleteStackTaskIPv6(TestDeleteStackTask,
                              HastexoIPv6TestCase):
    pass


class TestCheckStudentProgressTaskIPv6(TestCheckStudentProgressTask,
                                       HastexoIPv6TestCase):
    pass
