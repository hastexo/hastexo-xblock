import time
import json
from hastexo.hastexo import HastexoXBlock
from hastexo.utils import DEFAULT_SETTINGS, get_stack, update_stack

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
        self.block.provider = ""
        self.block.providers = [
            {"name": "provider1", "capacity": 1, "environment": "env1.yaml"},
            {"name": "provider2", "capacity": 2, "environment": "env2.yaml"},
            {"name": "provider3", "capacity": 0, "environment": "env3.yaml"}
        ]
        self.block.tests = ["bogus_test"]

        # Set on student view
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

    def update_stack(self, data):
        course_id, student_id = self.block.get_block_ids()
        update_stack(self.block.stack_name, course_id, student_id, data)

    def get_stack(self, prop=None):
        course_id, student_id = self.block.get_block_ids()
        return get_stack(self.block.stack_name, course_id, student_id, prop)

    def test_get_user_stack_status_first_time(self):
        self.init_block()

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)

    def test_launch_task_id_cleared_on_task_success(self):
        self.init_block()

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            self.call_handler("get_user_stack_status", data)

        self.assertEqual(self.get_stack("launch_task_id"), "")

    def test_launch_task_id_cleared_on_task_failure(self):
        self.init_block()

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            self.call_handler("get_user_stack_status", data)

        self.assertEqual(self.get_stack("launch_task_id"), "")

    def test_launch_task_id_not_cleared_on_pending_task(self):
        self.init_block()

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            self.call_handler("get_user_stack_status", data)

        self.assertNotEqual(self.get_stack("launch_task_id"), "")

    def test_get_user_stack_status_with_deprecated_provider(self):
        self.init_block()
        self.block.provider = "deprecated"
        self.block.providers = []

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)

    def test_get_user_stack_status_with_default_provider(self):
        self.init_block()
        self.block.provider = ""
        self.block.providers = []
        providers = {"default": {}}

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            with patch.dict(DEFAULT_SETTINGS,
                            {'providers': providers}):
                data = {
                    "initialize": True,
                    "reset": False
                }
                result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)

    def test_get_user_stack_status_without_default_provider(self):
        self.init_block()
        self.block.provider = ""
        self.block.providers = []
        providers = {"provider": {}}

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            with patch.dict(DEFAULT_SETTINGS,
                            {'providers': providers}):
                data = {
                    "initialize": True,
                    "reset": False
                }
                result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)

    def test_get_user_stack_status_with_no_providers(self):
        self.init_block()
        self.block.provider = ""
        self.block.providers = []
        providers = {}

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            with patch.dict(DEFAULT_SETTINGS,
                            {'providers': providers}):
                data = {
                    "initialize": True,
                    "reset": False
                }
                result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)

    def test_get_user_stack_status_resume_after_suspend(self):
        self.init_block()

        suspend_timeout = DEFAULT_SETTINGS.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=suspend_timeout)
        suspend_timestamp = timezone.now() - timedelta
        self.update_stack({
            "suspend_timestamp": suspend_timestamp,
            "status": 'CREATE_COMPLETE'
        })

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "RESUME_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
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

        suspend_timeout = DEFAULT_SETTINGS.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout - 1))
        suspend_timestamp = timezone.now() - timedelta
        self.update_stack({
            "suspend_timestamp": suspend_timestamp,
            "status": 'CREATE_COMPLETE'
        })

        # Async result mock
        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "RESUME_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertNotEqual(result, mock_result.result)
        self.assertFalse(mock_launch_stack_task.called)

    def test_get_user_stack_status_reset_before_suspend(self):
        self.init_block()

        suspend_timeout = DEFAULT_SETTINGS.get("suspend_timeout")
        timedelta = timezone.timedelta(seconds=(suspend_timeout - 1))
        suspend_timestamp = timezone.now() - timedelta
        self.update_stack({
            "suspend_timestamp": suspend_timestamp,
            "status": 'RESUME_COMPLETE'
        })

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
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
