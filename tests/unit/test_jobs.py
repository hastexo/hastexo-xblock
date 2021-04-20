from mock import patch
from django.test import TestCase
from django.utils import timezone

from hastexo.jobs import SuspenderJob, ReaperJob
from hastexo.models import Stack, StackLog
from hastexo.provider import ProviderException
from hastexo.common import (
    CREATE_COMPLETE,
    SUSPEND_PENDING,
    DELETE_PENDING,
    DELETE_COMPLETE,
    DELETE_IN_PROGRESS,
)


class TestHastexoJobs(TestCase):
    def setUp(self):
        self.stack_states = {
            'CREATE_IN_PROGRESS',
            'CREATE_FAILED',
            'CREATE_COMPLETE',
            'SUSPEND_IN_PROGRESS',
            'SUSPEND_FAILED',
            'SUSPEND_COMPLETE',
            'RESUME_IN_PROGRESS',
            'RESUME_FAILED',
            'RESUME_COMPLETE',
            'DELETE_IN_PROGRESS',
            'DELETE_FAILED',
            'DELETE_COMPLETE'}

        # Create a set of mock stacks to be returned by the mock provider.
        self.stacks = {}
        for state in self.stack_states:
            stack = {"status": state,
                     "outputs": {"bogus": "value"}}
            self.stacks[state] = stack

        # Mock settings
        self.settings = {
            "suspend_timeout": 120,
            "suspend_concurrency": 1,
            "suspend_in_parallel": False,
            "delete_age": 14,
            "delete_attempts": 3,
            "sleep_timeout": 0,
        }
        self.student_id = 'bogus_student_id'
        self.course_id = 'bogus_course_id'
        self.stack_name = 'bogus_stack_name'

        # Patchers
        patchers = {
            "Provider": patch("hastexo.jobs.Provider"),
            "DeleteStackTask": patch("hastexo.jobs.DeleteStackTask"),
            "SuspendStackTask": patch("hastexo.jobs.SuspendStackTask"),
        }
        self.mocks = {}
        for mock_name, patcher in patchers.items():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)

    def get_suspend_task_mock(self):
        return self.mocks["SuspendStackTask"].return_value

    def get_delete_task_mock(self):
        return self.mocks["DeleteStackTask"].return_value

    def test_dont_suspend_stack_with_no_provider(self):
        # Setup
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = "RESUME_COMPLETE"
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            status=state
        )
        stack.save()
        mock_suspend_task = self.get_suspend_task_mock()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        mock_suspend_task.apply_async.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, state)

    def test_suspend_stack_for_the_first_time(self):
        # Setup
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = "CREATE_COMPLETE"
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider="provider1",
            status=state
        )
        stack.save()
        mock_suspend_task = self.get_suspend_task_mock()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        mock_suspend_task.apply_async.assert_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, SUSPEND_PENDING)

    def test_suspend_stack_for_the_second_time(self):
        # Setup
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = "RESUME_COMPLETE"
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider="provider1",
            status=state
        )
        stack.save()
        mock_suspend_task = self.get_suspend_task_mock()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        mock_suspend_task.apply_async.assert_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, SUSPEND_PENDING)

    def test_dont_suspend_unexistent_stack(self):
        # Setup
        mock_suspend_task = self.get_suspend_task_mock()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        mock_suspend_task.apply_async.assert_not_called()

    def test_dont_suspend_live_stack(self):
        # Setup
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout - 1))
        suspend_timestamp = timezone.now() - timedelta
        state = "CREATE_COMPLETE"
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider="provider1",
            status=state
        )
        stack.save()
        mock_suspend_task = self.get_suspend_task_mock()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        mock_suspend_task.apply_async.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, state)

    def test_dont_suspend_failed_stack(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = "RESUME_FAILED"
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider="provider1",
            status=state
        )
        stack.save()
        mock_suspend_task = self.get_suspend_task_mock()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        mock_suspend_task.apply_async.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, state)

    def test_dont_suspend_suspended_stack(self):
        # Setup
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = "SUSPEND_COMPLETE"
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider="provider1",
            status=state
        )
        stack.save()
        mock_suspend_task = self.get_suspend_task_mock()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        mock_suspend_task.apply_async.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, state)

    def test_suspend_concurrency(self):
        # Setup
        self.settings["suspend_concurrency"] = 2
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = "CREATE_COMPLETE"
        stack1_name = "bogus_stack_1"
        stack1 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack1_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider1",
            status=state
        )
        stack1.save()
        stack2_name = "bogus_stack_2"
        stack2 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack2_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider2",
            status=state
        )
        stack2.save()
        stack3_name = "bogus_stack_3"
        stack3 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack3_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider3",
            status=state
        )
        stack3.save()
        mock_suspend_task = self.get_suspend_task_mock()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        self.assertEqual(2, len(mock_suspend_task.apply_async.mock_calls))
        stack1 = Stack.objects.get(name=stack1_name)
        self.assertEqual(stack1.status, SUSPEND_PENDING)
        stack2 = Stack.objects.get(name=stack2_name)
        self.assertEqual(stack2.status, SUSPEND_PENDING)
        stack3 = Stack.objects.get(name=stack3_name)
        self.assertEqual(stack3.status, state)

    def test_delete_old_stacks(self):
        # Setup
        delete_age = self.settings.get("delete_age") * 86400
        dont_delete_age = delete_age * 2
        suspend_timestamp = timezone.now() - timezone.timedelta(
            seconds=delete_age)
        dont_delete_timestamp = timezone.now() + timezone.timedelta(
            seconds=delete_age)
        state = "RESUME_COMPLETE"
        stack1_name = "bogus_stack_1"
        stack1 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack1_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider1",
            status=state,
            delete_age=delete_age,
            delete_by=suspend_timestamp
        )
        stack1.save()
        stack2_name = "bogus_stack_2"
        stack2 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack2_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider2",
            status=state,
            delete_age=delete_age,
            delete_by=suspend_timestamp
        )
        stack2.save()
        stack3_name = "bogus_stack_3"
        stack3 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack3_name,
            suspend_timestamp=suspend_timestamp,
            provider='provider3',
            status=state,
            delete_age=dont_delete_age,
            delete_by=dont_delete_timestamp
        )
        stack3.save()
        mock_delete_task = self.get_delete_task_mock()

        # Run
        job = ReaperJob(self.settings)
        job.run()

        # Assert
        self.assertEqual(2, len(mock_delete_task.apply_async.mock_calls))
        stack1 = Stack.objects.get(name=stack1_name)
        self.assertEqual(stack1.status, DELETE_PENDING)
        stack2 = Stack.objects.get(name=stack2_name)
        self.assertEqual(stack2.status, DELETE_PENDING)
        stack3 = Stack.objects.get(name=stack3_name)
        self.assertEqual(stack3.status, state)

    def test_dont_try_to_delete_certain_stack_states(self):
        # Setup
        delete_age = self.settings.get("delete_age") * 86400
        suspend_timestamp = timezone.now() - timezone.timedelta(
            seconds=delete_age)
        stack1_name = "bogus_stack_1"
        stack1 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack1_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider1",
            status=DELETE_PENDING,
            delete_age=delete_age,
            delete_by=suspend_timestamp
        )
        stack1.save()
        stack2_name = "bogus_stack_2"
        stack2 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack2_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider2",
            status=DELETE_IN_PROGRESS,
            delete_age=delete_age,
            delete_by=suspend_timestamp
        )
        stack2.save()
        stack3_name = "bogus_stack_3"
        stack3 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack3_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider3",
            status=DELETE_COMPLETE,
            delete_age=delete_age,
            delete_by=suspend_timestamp
        )
        stack3.save()
        stack4_name = "bogus_stack_4"
        stack4 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack4_name,
            suspend_timestamp=suspend_timestamp,
            status="CREATE_FAILED",
            delete_age=delete_age,
            delete_by=suspend_timestamp
        )
        stack4.save()
        stack5_name = "bogus_stack_5"
        stack5 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack5_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider2",
            status=CREATE_COMPLETE,
            delete_age=delete_age,
            delete_by=suspend_timestamp
        )
        stack5.save()
        stack6_name = "bogus_stack_6"
        stack6 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack6_name,
            suspend_timestamp=suspend_timestamp,
            provider="provider3",
            status="LAUNCH_PENDING",
            delete_age=delete_age,
            delete_by=suspend_timestamp
        )
        stack6.save()
        mock_delete_task = self.get_delete_task_mock()

        # Run
        job = ReaperJob(self.settings)
        job.run()

        # Assert
        mock_delete_task.apply_async.assert_not_called()
        stack1 = Stack.objects.get(name=stack1_name)
        self.assertEqual(stack1.status, DELETE_PENDING)
        stack2 = Stack.objects.get(name=stack2_name)
        self.assertEqual(stack2.status, DELETE_IN_PROGRESS)
        stack3 = Stack.objects.get(name=stack3_name)
        self.assertEqual(stack3.status, DELETE_COMPLETE)
        stack4 = Stack.objects.get(name=stack4_name)
        self.assertEqual(stack4.status, "CREATE_FAILED")
        stack5 = Stack.objects.get(name=stack5_name)
        self.assertEqual(stack5.status, CREATE_COMPLETE)
        stack6 = Stack.objects.get(name=stack6_name)
        self.assertEqual(stack6.status, "LAUNCH_PENDING")

    def test_delete_if_age_is_zero(self):
        # Setup
        suspend_timestamp = timezone.now()
        state = 'SUSPEND_COMPLETE'
        stack_name = 'bogus_stack'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack_name,
            suspend_timestamp=suspend_timestamp,
            provider='provider1',
            status=state,
            delete_age=0,
            delete_by=suspend_timestamp
        )
        stack.save()
        mock_delete_task = self.get_delete_task_mock()

        # Run
        job = ReaperJob(self.settings)
        job.run()

        mock_delete_task.apply_async.assert_called()
        stack = Stack.objects.get(name=stack_name)
        self.assertEqual(stack.status, 'DELETE_PENDING')

    def test_destroy_zombies(self):
        # Setup
        delete_age = self.settings.get("delete_age")
        delete_delta = timezone.timedelta(days=(delete_age + 1))
        delete_timestamp = timezone.now() - delete_delta
        dont_delete_delta = timezone.timedelta(days=(delete_age - 1))
        dont_delete_timestamp = timezone.now() - dont_delete_delta
        stack_names = (
            'zombie_stack_1',
            'zombie_stack_2',
            'zombie_stack_3',
            'zombie_stack_4',
            'not_a_zombie_stack'
        )

        # Create zombie stacks
        for i in range(0, 4):
            _stack = Stack(
                student_id=self.student_id,
                course_id=self.course_id,
                name=stack_names[i],
                suspend_timestamp=delete_timestamp,
                status=DELETE_COMPLETE
            )
            _stack.save()

        # Create living stack
        _stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack_names[4],
            suspend_timestamp=dont_delete_timestamp,
            status=CREATE_COMPLETE
        )
        _stack.save()

        mock_provider = self.mocks["Provider"].init.return_value
        provider1_stacks = []
        for i in range(0, 3):
            provider1_stacks.append({
                "name": stack_names[i],
                "status": CREATE_COMPLETE
            })
        provider2_stacks = []
        for i in range(3, 5):
            provider2_stacks.append({
                "name": stack_names[i],
                "status": CREATE_COMPLETE
            })
        provider3_stacks = [{
            "name": "unknown",
            "status": CREATE_COMPLETE
        }]
        mock_provider.get_stacks.side_effect = [
            provider1_stacks,
            provider2_stacks,
            provider3_stacks
        ]
        self.settings["providers"] = {
            "provider1": {},
            "provider2": {},
            "provider3": {}
        }
        mock_delete_task = self.get_delete_task_mock()

        # Run
        job = ReaperJob(self.settings)
        job.run()

        # Assert
        self.assertEqual(4, len(mock_delete_task.apply_async.mock_calls))
        stack = Stack.objects.get(name=stack_names[0])
        self.assertEqual(stack.status, DELETE_PENDING)
        stack = Stack.objects.get(name=stack_names[1])
        self.assertEqual(stack.status, DELETE_PENDING)
        stack = Stack.objects.get(name=stack_names[2])
        self.assertEqual(stack.status, DELETE_PENDING)
        stack = Stack.objects.get(name=stack_names[3])
        self.assertEqual(stack.status, DELETE_PENDING)
        stack = Stack.objects.get(name=stack_names[4])
        self.assertEqual(stack.status, CREATE_COMPLETE)

    def test_exception_destroying_zombies(self):
        # Setup
        mock_provider = self.mocks["Provider"].init.return_value
        mock_provider.get_stacks.side_effect = ProviderException("")
        self.settings["providers"] = {"provider": {}}

        # Run
        job = ReaperJob(self.settings)
        job.run()

    def test_stack_log(self):
        # Setup
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'CREATE_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            provider='provider1',
            name=self.stack_name
        )
        stack.status = state
        stack.save()

        # Run
        job = SuspenderJob(self.settings)
        job.run()

        # Assert
        stacklog = StackLog.objects.filter(stack_id=stack.id)
        states = [logentry.status for logentry in stacklog]
        expected_states = [
            state,
            SUSPEND_PENDING
        ]
        self.assertEqual(states, expected_states)
