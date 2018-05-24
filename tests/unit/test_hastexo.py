import time
import json
from hastexo.hastexo import HastexoXBlock
from hastexo.models import Stack
from hastexo.utils import DEFAULT_SETTINGS

from mock import Mock, patch, DEFAULT
from webob import Request
from django.test import TestCase
from django.utils import timezone
from workbench.runtime import WorkbenchRuntime
from xblock.fields import ScopeIds
from xblock.runtime import KvsFieldData, DictKeyValueStore


def make_request(data, method='POST'):
    """
    Make a webob JSON request

    """
    request = Request.blank('/')
    request.method = 'POST'
    request.body = json.dumps(data).encode('utf-8') if data is not None else ""
    request.method = method
    return request


class TestHastexoXBlock(TestCase):
    """
    Basic unit tests for the Hastexo XBlock.

    """
    def call_handler(self,
                     handler_name,
                     data=None,
                     expect_json=True,
                     method='POST'):
        response = self.block.handle(handler_name,
                                     make_request(data, method=method))
        if expect_json:
            self.assertEqual(response.status_code, 200)
            return json.loads(response.body)
        return response

    def init_block(self):
        # Block settings
        self.block.stack_template_path = "bogus_template_path"
        self.block.stack_user_name = "bogus_user"
        self.block.provider = "default"
        self.block.tests = ["bogus_test"]

        # Set on student view
        self.block.configuration = self.block.get_configuration()
        self.block.stack_name = "bogus_stack"

    def setUp(self):
        block_type = 'hastexo'
        key_store = DictKeyValueStore()
        field_data = KvsFieldData(key_store)
        runtime = WorkbenchRuntime()
        def_id = runtime.id_generator.create_definition(block_type)
        usage_id = runtime.id_generator.create_usage(def_id)
        scope_ids = ScopeIds('user', block_type, def_id, usage_id)

        self.block = HastexoXBlock(runtime,
                                   field_data,
                                   scope_ids=scope_ids)

    def test_get_configuration(self):
        """
        Test the get_configuration() method.

        """
        configuration = self.block.get_configuration()
        self.assertIn("launch_timeout", configuration)
        self.assertIn("suspend_timeout", configuration)
        self.assertIn("terminal_url", configuration)
        self.assertIn("js_timeouts", configuration)
        self.assertIn("credentials", configuration)
        self.assertNotIn("providers", configuration)

    def test_get_user_stack_status_first_time(self):
        self.init_block()

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_get_stack_template = Mock(return_value=('bogus_stack_template'))

        with patch.multiple(self.block,
                            launch_stack_task=mock_launch_stack_task,
                            get_stack_template=mock_get_stack_template):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)

    def test_get_user_stack_status_resume_after_suspend(self):
        self.init_block()

        suspend_timeout = self.block.configuration.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=suspend_timeout)
        suspend_timestamp = timezone.now() - timedelta
        course_id, student_id = self.block.get_block_ids()
        stack, _ = Stack.objects.get_or_create(
            student_id=student_id,
            course_id=course_id,
            name=self.block.stack_name,
            suspend_timestamp=suspend_timestamp,
            status='CREATE_COMPLETE'
        )

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "RESUME_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_get_stack_template = Mock(return_value=('bogus_stack_template'))

        with patch.multiple(self.block,
                            launch_stack_task=mock_launch_stack_task,
                            get_stack_template=mock_get_stack_template):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)

    def test_get_user_stack_status_dont_resume_before_suspend(self):
        # Initialize block
        self.init_block()

        suspend_timeout = self.block.configuration.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout - 1))
        suspend_timestamp = timezone.now() - timedelta
        course_id, student_id = self.block.get_block_ids()
        stack, _ = Stack.objects.get_or_create(
            student_id=student_id,
            course_id=course_id,
            name=self.block.stack_name,
            suspend_timestamp=suspend_timestamp,
            status='CREATE_COMPLETE'
        )

        # Async result mock
        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "RESUME_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_get_stack_template = Mock(return_value=('bogus_stack_template'))

        with patch.multiple(self.block,
                            launch_stack_task=mock_launch_stack_task,
                            get_stack_template=mock_get_stack_template):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertNotEqual(result, mock_result.result)
        self.assertFalse(mock_launch_stack_task.called)

    def test_get_user_stack_status_reset_before_suspend(self):
        self.init_block()

        suspend_timeout = self.block.configuration.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout - 1))
        suspend_timestamp = timezone.now() - timedelta
        course_id, student_id = self.block.get_block_ids()
        stack, _ = Stack.objects.get_or_create(
            student_id=student_id,
            course_id=course_id,
            name=self.block.stack_name,
            suspend_timestamp=suspend_timestamp,
            status='RESUME_COMPLETE'
        )

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_get_stack_template = Mock(return_value=('bogus_stack_template'))

        with patch.multiple(self.block,
                            launch_stack_task=mock_launch_stack_task,
                            get_stack_template=mock_get_stack_template):
            data = {
                "initialize": True,
                "reset": True
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)

    def test_get_check_status(self):
        self.init_block()
        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {
            "status": 'CHECK_PROGRESS_COMPLETE',
            "pass": 1,
            "total": 1
        }
        with patch.object(self.block, 'check_progress_task') as mock_task:
            with patch.object(self.block.runtime, 'publish') as mock_publish:
                mock_task.return_value = mock_result
                result = self.call_handler("get_check_status", {})
                self.assertEqual(result, mock_result.result)
                self.assertTrue(mock_task.called)
                mock_publish.assert_called_once_with(
                    self.block,
                    'grade',
                    {'value': 1, 'max_value': 1}
                )

    def test_get_check_status_doesnt_go_on_forever(self):
        self.init_block()
        mock_result = Mock()
        mock_result.ready.return_value = False
        check_timeout = 1

        with patch.multiple(self.block,
                            check_progress_task=DEFAULT,
                            check_progress_task_result=DEFAULT) as mocks:
            with patch.dict(DEFAULT_SETTINGS,
                            {'check_timeout': check_timeout}):
                mocks['check_progress_task'].return_value = mock_result
                mocks['check_progress_task_result'].return_value = mock_result
                result = self.call_handler("get_check_status", {})
                self.assertEqual(result['status'], 'CHECK_PROGRESS_PENDING')
                result = self.call_handler("get_check_status", {})
                self.assertEqual(result['status'], 'CHECK_PROGRESS_PENDING')
                time.sleep(check_timeout)
                result = self.call_handler("get_check_status", {})
                self.assertEqual(result['status'], 'ERROR')
