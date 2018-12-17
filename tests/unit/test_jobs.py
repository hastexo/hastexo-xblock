from mock import Mock, patch, call
from django.test import TestCase
from django.utils import timezone
from heatclient.exc import HTTPException, HTTPNotFound

from hastexo.jobs import SuspenderJob, ReaperJob
from hastexo.models import Stack, StackLog
from hastexo.utils import (SUSPEND_ISSUED_STATE, DELETE_STATE, DELETED_STATE,
                           SUSPEND_RETRY_STATE, DELETE_IN_PROGRESS_STATE,
                           DELETE_FAILED_STATE)


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

        # Create a set of mock stacks to be returned by the heat client mock.
        self.stacks = {}
        for state in self.stack_states:
            stack = Mock()
            stack.stack_status = state
            stack.id = "%s_ID" % state
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
            "suspend_timeout": 120,
            "suspend_concurrency": 1,
            "suspend_in_parallel": False,
            "delete_age": 14,
            "delete_attempts": 3,
            "task_timeouts": {
                "sleep": 0,
                "retries": 10
            },
            "providers": {
                "provider1": mock_credentials,
                "provider2": mock_credentials,
                "provider3": mock_credentials
            }
        }
        self.student_id = 'bogus_student_id'
        self.course_id = 'bogus_course_id'
        self.stack_name = 'bogus_stack_name'

    def test_dont_suspend_stack_with_no_provider(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'RESUME_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [self.stacks[state]]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, state)

    def test_suspend_stack_for_the_first_time(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'CREATE_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [self.stacks[state]]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_called_with(
            stack_id=self.stack_name
        )
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, SUSPEND_ISSUED_STATE)

    def test_suspend_stack_for_the_second_time(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'RESUME_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks[state]
        ]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_called_with(
            stack_id=self.stack_name
        )
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, SUSPEND_ISSUED_STATE)

    def test_dont_suspend_unexistent_stack(self):
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            HTTPNotFound
        ]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_not_called()

    def test_dont_suspend_live_stack(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout - 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'CREATE_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [self.stacks[state]]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, state)

    def test_dont_suspend_failed_stack(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'RESUME_FAILED'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [self.stacks[state]]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, state)

    def test_dont_suspend_suspended_stack(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'SUSPEND_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [self.stacks[state]]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, state)

    def test_dont_suspend_deleted_stack(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'RESUME_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [HTTPNotFound]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, DELETED_STATE)

    def test_retry_suspending_stack(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'RESUME_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['SUSPEND_IN_PROGRESS']
        ]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, SUSPEND_RETRY_STATE)

    def test_retry_on_exception(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'RESUME_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [self.stacks[state]]
        mock_heat_client.actions.suspend.side_effect = [HTTPException]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        stack = Stack.objects.get(name=self.stack_name)
        self.assertEqual(stack.status, SUSPEND_RETRY_STATE)

    def test_dont_retry_failed_stack(self):
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'RESUME_COMPLETE'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            suspend_timestamp=suspend_timestamp,
            name=self.stack_name,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['RESUME_FAILED']
        ]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_not_called()
        stack = Stack.objects.get(name=self.stack_name)
        self.assertNotEqual(stack.status, SUSPEND_RETRY_STATE)

    def test_suspend_concurrency(self):
        self.settings["suspend_concurrency"] = 2
        suspend_timeout = self.settings.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout + 1))
        suspend_timestamp = timezone.now() - timedelta
        state = 'CREATE_COMPLETE'
        stack1_name = 'bogus_stack_1'
        stack1 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack1_name,
            suspend_timestamp=suspend_timestamp,
            provider='provider1',
            status=state
        )
        stack1.save()
        stack2_name = 'bogus_stack_2'
        stack2 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack2_name,
            suspend_timestamp=suspend_timestamp,
            provider='provider2',
            status=state
        )
        stack2.save()
        stack3_name = 'bogus_stack_3'
        stack3 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack3_name,
            suspend_timestamp=suspend_timestamp,
            provider='provider3',
            status=state
        )
        stack3.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks[state],
            self.stacks[state]
        ]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.actions.suspend.assert_has_calls([
            call(stack_id=stack1_name),
            call(stack_id=stack2_name)
        ])
        self.assertNotIn(
            call(stack_id=stack3_name),
            mock_heat_client.actions.suspend.mock_calls
        )
        stack1 = Stack.objects.get(name=stack1_name)
        self.assertEqual(stack1.status, SUSPEND_ISSUED_STATE)
        stack2 = Stack.objects.get(name=stack2_name)
        self.assertEqual(stack2.status, SUSPEND_ISSUED_STATE)
        stack3 = Stack.objects.get(name=stack3_name)
        self.assertEqual(stack3.status, state)

    def test_delete_old_stacks(self):
        delete_age = self.settings.get("delete_age")
        delete_delta = timezone.timedelta(days=(delete_age + 1))
        delete_timestamp = timezone.now() - delete_delta
        dont_delete_delta = timezone.timedelta(days=(delete_age - 1))
        dont_delete_timestamp = timezone.now() - dont_delete_delta
        state = 'RESUME_COMPLETE'
        stack1_name = 'bogus_stack_1'
        stack1 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack1_name,
            suspend_timestamp=delete_timestamp,
            provider='provider1',
            status=state
        )
        stack1.save()
        stack2_name = 'bogus_stack_2'
        stack2 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack2_name,
            suspend_timestamp=delete_timestamp,
            provider='provider2',
            status=state
        )
        stack2.save()
        stack3_name = 'bogus_stack_3'
        stack3 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack3_name,
            suspend_timestamp=dont_delete_timestamp,
            provider='provider3',
            status=state
        )
        stack3.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks[state],
            self.stacks[DELETE_IN_PROGRESS_STATE],
            HTTPNotFound,
            self.stacks[state],
            self.stacks[DELETE_IN_PROGRESS_STATE],
            HTTPNotFound
        ]

        job = ReaperJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.stacks.delete.assert_has_calls([
            call(stack_id=stack1_name),
            call(stack_id=stack2_name)
        ])
        self.assertNotIn(
            call(stack_id=stack3_name),
            mock_heat_client.stacks.delete.mock_calls
        )
        stack1 = Stack.objects.get(name=stack1_name)
        self.assertEqual(stack1.status, DELETED_STATE)
        stack2 = Stack.objects.get(name=stack2_name)
        self.assertEqual(stack2.status, DELETED_STATE)
        stack3 = Stack.objects.get(name=stack3_name)
        self.assertEqual(stack3.status, state)

    def test_delete_exception_doesnt_hold_up_the_queue(self):
        delete_age = self.settings.get("delete_age")
        delete_delta = timezone.timedelta(days=(delete_age + 1))
        delete_timestamp = timezone.now() - delete_delta
        state = 'RESUME_COMPLETE'
        stack1_name = 'bogus_stack_1'
        stack1 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack1_name,
            suspend_timestamp=delete_timestamp,
            provider='provider1',
            status=state
        )
        stack1.save()
        stack2_name = 'bogus_stack_2'
        stack2 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack2_name,
            suspend_timestamp=delete_timestamp,
            provider='provider2',
            status=state
        )
        stack2.save()
        stack3_name = 'bogus_stack_3'
        stack3 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack3_name,
            suspend_timestamp=delete_timestamp,
            provider='provider3',
            status=state
        )
        stack3.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks[state],
            self.stacks[DELETE_IN_PROGRESS_STATE],
            HTTPNotFound,
            self.stacks[state],
            self.stacks[state],
            self.stacks[DELETE_IN_PROGRESS_STATE],
            HTTPNotFound
        ]
        mock_heat_client.stacks.delete.side_effect = [
            True,
            HTTPException,
            True
        ]

        job = ReaperJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.stacks.delete.assert_has_calls([
            call(stack_id=stack1_name),
            call(stack_id=stack2_name),
            call(stack_id=stack3_name)
        ])
        stack1 = Stack.objects.get(name=stack1_name)
        self.assertEqual(stack1.status, DELETED_STATE)
        stack2 = Stack.objects.get(name=stack2_name)
        self.assertEqual(stack2.status, state)
        stack3 = Stack.objects.get(name=stack3_name)
        self.assertEqual(stack3.status, DELETED_STATE)

    def test_dont_try_to_delete_certain_stack_states(self):
        delete_age = self.settings.get("delete_age")
        delete_delta = timezone.timedelta(days=(delete_age + 1))
        delete_timestamp = timezone.now() - delete_delta
        stack1_name = 'bogus_stack_1'
        stack1 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack1_name,
            suspend_timestamp=delete_timestamp,
            provider='provider1',
            status=DELETE_STATE
        )
        stack1.save()
        stack2_name = 'bogus_stack_2'
        stack2 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack2_name,
            suspend_timestamp=delete_timestamp,
            provider='provider2',
            status=DELETE_IN_PROGRESS_STATE
        )
        stack2.save()
        stack3_name = 'bogus_stack_3'
        stack3 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack3_name,
            suspend_timestamp=delete_timestamp,
            provider='provider3',
            status=DELETED_STATE
        )
        stack3.save()
        stack4_name = 'bogus_stack_4'
        stack4 = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack4_name,
            suspend_timestamp=delete_timestamp,
            status='CREATE_FAILED'
        )
        stack4.save()
        mock_heat_client = Mock()

        job = ReaperJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.stacks.delete.assert_not_called()
        stack1 = Stack.objects.get(name=stack1_name)
        self.assertEqual(stack1.status, DELETE_STATE)
        stack2 = Stack.objects.get(name=stack2_name)
        self.assertEqual(stack2.status, DELETE_IN_PROGRESS_STATE)
        stack3 = Stack.objects.get(name=stack3_name)
        self.assertEqual(stack3.status, DELETED_STATE)
        stack4 = Stack.objects.get(name=stack4_name)
        self.assertEqual(stack4.status, 'CREATE_FAILED')

    def test_dont_wait_forever_for_deletion(self):
        delete_age = self.settings.get("delete_age")
        delete_delta = timezone.timedelta(days=(delete_age + 1))
        delete_timestamp = timezone.now() - delete_delta
        state = 'RESUME_COMPLETE'
        stack_name = 'bogus_stack'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack_name,
            suspend_timestamp=delete_timestamp,
            provider='provider1'
        )
        stack.status = state
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks[state],
            self.stacks[DELETE_IN_PROGRESS_STATE],
            self.stacks[DELETE_IN_PROGRESS_STATE],
            self.stacks[DELETE_IN_PROGRESS_STATE]
        ]

        self.settings['task_timeouts']['retries'] = 3
        job = ReaperJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.stacks.delete.assert_called_with(
            stack_id=stack_name
        )
        stack = Stack.objects.get(name=stack_name)
        self.assertEqual(stack.status, DELETE_FAILED_STATE)

    def test_dont_delete_if_age_is_zero(self):
        self.settings["delete_age"] = 0
        delete_delta = timezone.timedelta(days=15)
        delete_timestamp = timezone.now() - delete_delta
        state = 'RESUME_COMPLETE'
        stack_name = 'bogus_stack'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack_name,
            suspend_timestamp=delete_timestamp,
            provider='provider1',
            status=state
        )
        stack.save()
        mock_heat_client = Mock()

        job = ReaperJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.stacks.delete.assert_not_called()
        stack = Stack.objects.get(name=stack_name)
        self.assertEqual(stack.status, state)

    def test_retry_deletion(self):
        delete_age = self.settings.get("delete_age")
        delete_delta = timezone.timedelta(days=(delete_age + 1))
        delete_timestamp = timezone.now() - delete_delta
        state = 'RESUME_COMPLETE'
        stack_name = 'bogus_stack'
        stack = Stack(
            student_id=self.student_id,
            course_id=self.course_id,
            name=stack_name,
            suspend_timestamp=delete_timestamp,
            provider='provider1'
        )
        stack.status = state
        stack.save()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks[state],
            self.stacks[DELETE_FAILED_STATE],
            self.stacks[DELETE_FAILED_STATE],
            self.stacks[DELETE_FAILED_STATE]
        ]

        job = ReaperJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        mock_heat_client.stacks.delete.assert_has_calls([
            call(stack_id=stack_name),
            call(stack_id=stack_name),
            call(stack_id=stack_name)
        ])
        stack = Stack.objects.get(name=stack_name)
        self.assertEqual(stack.status, DELETE_FAILED_STATE)

    def test_stack_log(self):
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
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [self.stacks[state]]

        job = SuspenderJob(self.settings)
        with patch.multiple(
                job,
                get_heat_client=Mock(return_value=mock_heat_client)):
            job.run()

        stacklog = StackLog.objects.filter(stack_id=stack.id)
        states = [l.status for l in stacklog]
        expected_states = [state,
                           'SUSPEND_PENDING',
                           'SUSPEND_ISSUED']
        self.assertEqual(states, expected_states)
