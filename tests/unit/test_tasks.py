from unittest import TestCase
from mock import Mock, patch
from heatclient.exc import HTTPNotFound
from hastexo.tasks import LaunchStackTask, SuspendStackTask
from hastexo.tasks import CheckStudentProgressTask


class TestHastexoTasks(TestCase):
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

        # Mock settings
        self.configuration = {
            "launch_timeout": 300,
            "suspend_timeout": 120,
            "terminal_url": "/terminal",
            "ssh_dir": "/edx/var/edxapp/terminal_users/ANONYMOUS/.ssh",
            "ssh_upload": False,
            "ssh_bucket": "identities",
            "task_timeouts": {
                "sleep": 0,
                "retries": 10
            },
            "js_timeouts": {
                "status": 10000,
                "keepalive": 15000,
                "idle": 600000,
                "check": 5000
            },
            "credentials": {
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
        }
        self.stack_name = 'bogus_stack_name'
        self.stack_template = 'bogus_stack_template'
        self.stack_user = 'bogus_stack_user'
        self.stack_ip = '127.0.0.1'

    def test_create_stack_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_COMPLETE']
        ]
        mock_heat_client.stacks.create.return_value = {
            'stack': {'id': self.stack_name}
        }
        mock_verify_stack = Mock(return_value=('VERIFY_COMPLETE',
                                               None,
                                               self.stack_ip))
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client),  # noqa: E501
                            verify_stack=mock_verify_stack):
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                False
            )
            assert res['status'] == 'CREATE_COMPLETE'
            mock_heat_client.stacks.create.assert_called_with(
                stack_name=self.stack_name,
                template=self.stack_template
            )
            mock_verify_stack.assert_called_with(
                self.configuration,
                self.stacks['CREATE_COMPLETE'],
                self.stack_name,
                self.stack_user
            )

    def test_reset_stack_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['RESUME_FAILED'],
            self.stacks['DELETE_IN_PROGRESS'],
            HTTPNotFound,
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_COMPLETE']
        ]
        mock_heat_client.stacks.create.return_value = {
            'stack': {'id': self.stack_name}
        }
        mock_verify_stack = Mock(return_value=('VERIFY_COMPLETE',
                                               None,
                                               self.stack_ip))
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client),  # noqa: E501
                            verify_stack=mock_verify_stack):
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                True
            )
            mock_heat_client.stacks.delete.assert_called_with(
                stack_id=self.stacks['RESUME_FAILED'].id
            )
            mock_heat_client.stacks.create.assert_called_with(
                stack_name=self.stack_name,
                template=self.stack_template
            )
            mock_verify_stack.assert_called_with(
                self.configuration,
                self.stacks['CREATE_COMPLETE'],
                self.stack_name,
                self.stack_user
            )
            assert res['status'] == 'CREATE_COMPLETE'

    def test_dont_reset_new_stack_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_COMPLETE']
        ]
        mock_heat_client.stacks.create.return_value = {
            'stack': {'id': self.stack_name}
        }
        mock_verify_stack = Mock(return_value=('VERIFY_COMPLETE',
                                               None,
                                               self.stack_ip))
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client),  # noqa: E501
                            verify_stack=mock_verify_stack):
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                True
            )
            mock_heat_client.stacks.delete.assert_not_called()
            mock_heat_client.stacks.create.assert_called_with(
                stack_name=self.stack_name,
                template=self.stack_template
            )
            mock_verify_stack.assert_called_with(
                self.configuration,
                self.stacks['CREATE_COMPLETE'],
                self.stack_name,
                self.stack_user
            )
            assert res['status'] == 'CREATE_COMPLETE'

    def test_resume_suspended_stack_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['SUSPEND_COMPLETE'],
            self.stacks['RESUME_IN_PROGRESS'],
            self.stacks['RESUME_IN_PROGRESS'],
            self.stacks['RESUME_COMPLETE']
        ]
        mock_verify_stack = Mock(return_value=('VERIFY_COMPLETE',
                                               None,
                                               self.stack_ip))
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client),  # noqa: E501
                            verify_stack=mock_verify_stack):
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                False
            )
            assert res['status'] == 'RESUME_COMPLETE'
            mock_heat_client.actions.resume.assert_called_with(
                stack_id=self.stacks['SUSPEND_COMPLETE'].id
            )
            mock_verify_stack.assert_called_with(
                self.configuration,
                self.stacks['RESUME_COMPLETE'],
                self.stack_name,
                self.stack_user
            )

    def test_resume_suspending_stack_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['SUSPEND_IN_PROGRESS'],
            self.stacks['SUSPEND_IN_PROGRESS'],
            self.stacks['SUSPEND_COMPLETE'],
            self.stacks['RESUME_IN_PROGRESS'],
            self.stacks['RESUME_IN_PROGRESS'],
            self.stacks['RESUME_COMPLETE']
        ]
        mock_verify_stack = Mock(return_value=('VERIFY_COMPLETE',
                                               None,
                                               self.stack_ip))
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client),  # noqa: E501
                            verify_stack=mock_verify_stack):
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                False
            )
            assert res['status'] == 'RESUME_COMPLETE'
            mock_heat_client.actions.resume.assert_called_with(
                stack_id=self.stacks['SUSPEND_COMPLETE'].id
            )
            mock_verify_stack.assert_called_with(
                self.configuration,
                self.stacks['RESUME_COMPLETE'],
                self.stack_name,
                self.stack_user
            )

    def test_delete_stack_on_create_failed_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_FAILED']
        ]
        mock_heat_client.stacks.create.return_value = {
            'stack': {'id': self.stack_name}
        }
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                False
            )
            assert res['status'] == 'CREATE_FAILED'
            mock_heat_client.stacks.delete.assert_called_with(
                stack_id=self.stacks['CREATE_FAILED'].id
            )

    def test_dont_wait_forever_for_suspension_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['SUSPEND_IN_PROGRESS'],
            self.stacks['SUSPEND_IN_PROGRESS'],
            self.stacks['SUSPEND_IN_PROGRESS'],
            self.stacks['SUSPEND_IN_PROGRESS'],
            self.stacks['SUSPEND_IN_PROGRESS']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            self.configuration['task_timeouts']['retries'] = 3
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                False
            )
            assert res['status'] == 'SUSPEND_FAILED'
            mock_heat_client.stacks.delete.assert_not_called()

    def test_dont_wait_forever_for_creation_and_delete_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            HTTPNotFound,
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS']
        ]
        mock_heat_client.stacks.create.return_value = {
            'stack': {'id': self.stack_name}
        }
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            self.configuration['task_timeouts']['retries'] = 3
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                False
            )
            assert res['status'] == 'CREATE_FAILED'
            mock_heat_client.stacks.delete.assert_called_with(
                stack_id=self.stacks['CREATE_IN_PROGRESS'].id
            )

    def test_exit_resume_failed_exit_status_during_launch(self):
        task = LaunchStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['SUSPEND_COMPLETE'],
            self.stacks['RESUME_IN_PROGRESS'],
            self.stacks['RESUME_IN_PROGRESS'],
            self.stacks['RESUME_FAILED']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            res = task.run(
                self.configuration,
                self.stack_name,
                self.stack_template,
                self.stack_user,
                False
            )
            assert res['status'] == 'RESUME_FAILED'

    def test_suspend_stack_for_the_first_time(self):
        task = SuspendStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['CREATE_COMPLETE']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            task.run(self.configuration, self.stack_name)
            mock_heat_client.actions.suspend.assert_called_with(
                stack_id=self.stack_name
            )

    def test_suspend_stack_for_the_second_time(self):
        task = SuspendStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['RESUME_COMPLETE']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            task.run(self.configuration, self.stack_name)
            mock_heat_client.actions.suspend.assert_called_with(
                stack_id=self.stack_name
            )

    def test_dont_suspend_unexistent_stack(self):
        task = SuspendStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            HTTPNotFound
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            task.run(self.configuration, self.stack_name)
            mock_heat_client.actions.suspend.assert_not_called()

    def test_dont_suspend_failed_stack(self):
        task = SuspendStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['RESUME_FAILED']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            task.run(self.configuration, self.stack_name)
            mock_heat_client.actions.suspend.assert_not_called()

    def test_dont_suspend_suspending_stack(self):
        task = SuspendStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['SUSPEND_IN_PROGRESS']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            task.run(self.configuration, self.stack_name)
            mock_heat_client.actions.suspend.assert_not_called()

    def test_dont_suspend_suspended_stack(self):
        task = SuspendStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['SUSPEND_COMPLETE']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            task.run(self.configuration, self.stack_name)
            mock_heat_client.actions.suspend.assert_not_called()

    def test_wait_for_create_during_suspend(self):
        task = SuspendStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_COMPLETE']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            task.run(self.configuration, self.stack_name)
            mock_heat_client.actions.suspend.assert_called_with(
                stack_id=self.stack_name
            )

    def test_dont_wait_forever_during_suspend(self):
        task = SuspendStackTask()
        mock_heat_client = Mock()
        mock_heat_client.stacks.get.side_effect = [
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS'],
            self.stacks['CREATE_IN_PROGRESS']
        ]
        with patch.multiple(task,
                            get_heat_client=Mock(return_value=mock_heat_client)):  # noqa: E501
            self.configuration['task_timeouts']['retries'] = 3
            task.run(self.configuration, self.stack_name)
            mock_heat_client.actions.suspend.assert_not_called()

    def test_check_student_progress(self):
        task = CheckStudentProgressTask()
        mock_ssh = Mock()
        mock_stdout_pass = Mock()
        mock_stdout_pass.channel.recv_exit_status.return_value = 0
        mock_stdout_fail = Mock()
        mock_stdout_fail.channel.recv_exit_status.return_value = 1
        mock_ssh.exec_command.side_effect = [
            (None, mock_stdout_pass, None),
            (None, mock_stdout_fail, None),
            (None, mock_stdout_pass, None)
        ]
        tests = [
            'test pass',
            'test fail',
            'test pass'
        ]
        with patch.object(task,
                          'open_ssh_connection',
                          Mock(return_value=mock_ssh)):
            res = task.run(
                self.configuration,
                tests,
                self.stack_ip,
                self.stack_name,
                self.stack_user
            )
            assert res['status'] == 'COMPLETE'
            assert res['pass'] == 2
            assert res['total'] == 3
