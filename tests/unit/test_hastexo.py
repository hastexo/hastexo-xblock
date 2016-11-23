import json
import time
import unittest
import hastexo

from mock import Mock, patch
from webob import Request
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


class TestHastexoXBlock(unittest.TestCase):
    """
    Basic unit tests for the Hastexo XBlock.

    """
    def call_handler(self, handler_name, data=None, expect_json=True, method='POST'):
        response = self.block.handle(handler_name, make_request(data, method=method))
        if expect_json:
            self.assertEqual(response.status_code, 200)
            return json.loads(response.body)
        return response

    def init_block(self):
        # Block settings
        self.block.stack_template_path = "bogus_template_path"
        self.block.stack_user_name = "bogus_user"
        self.block.provider = "default"

        # Set on student view
        self.block.configuration = self.block.get_configuration()
        self.block.stack_name = "bogus_stack"
        self.block.stack_template = "bogus_template"

    def setUp(self):
        block_type = 'hastexo'
        key_store = DictKeyValueStore()
        field_data = KvsFieldData(key_store)
        runtime = WorkbenchRuntime()
        def_id = runtime.id_generator.create_definition(block_type)
        usage_id = runtime.id_generator.create_usage(def_id)
        scope_ids = ScopeIds('user', block_type, def_id, usage_id)

        self.block = hastexo.HastexoXBlock(runtime, field_data, scope_ids=scope_ids)

    def test_get_configuration(self):
        """
        Test the get_configuration() method.

        """
        configuration = self.block.get_configuration()
        self.assertIn("launch_timeout", configuration)
        self.assertIn("suspend_timeout", configuration)
        self.assertIn("terminal_url", configuration)
        self.assertIn("ssh_dir", configuration)
        self.assertIn("ssh_upload", configuration)
        self.assertIn("ssh_bucket", configuration)
        self.assertIn("js_timeouts", configuration)
        self.assertIn("credentials", configuration)
        self.assertNotIn("providers", configuration)

    def test_get_user_stack_status_first_time(self):
        self.init_block()

        mock_result = Mock()
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task=Mock(return_value=mock_result)
        mock_suspend_user_stack=Mock()

        with patch.multiple(self.block,
            launch_stack_task=mock_launch_stack_task,
            suspend_user_stack=mock_suspend_user_stack
        ):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)
        self.assertTrue(mock_suspend_user_stack.called)

    def test_get_user_stack_status_resume_after_suspend(self):
        self.init_block()

        now = int(time.time())
        suspend_timeout = self.block.configuration.get("suspend_timeout")
        suspend_timestamp = now - suspend_timeout
        self.block.stacks = {
            self.block.stack_name: {
                "suspend_timestamp": suspend_timestamp,
                "status": {"status": "CREATE_COMPLETE"}
            }
        }

        mock_result = Mock()
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "RESUME_COMPLETE"}
        mock_launch_stack_task=Mock(return_value=mock_result)
        mock_suspend_user_stack=Mock()

        with patch.multiple(self.block,
            launch_stack_task=mock_launch_stack_task,
            suspend_user_stack=mock_suspend_user_stack
        ):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)
        self.assertTrue(mock_suspend_user_stack.called)

    def test_get_user_stack_status_dont_resume_before_suspend(self):
        # Initialize block
        self.init_block()

        now = int(time.time())
        suspend_timeout = self.block.configuration.get("suspend_timeout")
        suspend_timestamp = now - suspend_timeout + 1
        self.block.stacks = {
            self.block.stack_name: {
                "suspend_timestamp": suspend_timestamp,
                "status": {"status": "CREATE_COMPLETE"}
            }
        }
        # Async result mock
        mock_result = Mock()
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "RESUME_COMPLETE"}
        mock_launch_stack_task=Mock(return_value=mock_result)
        mock_suspend_user_stack=Mock()

        with patch.multiple(self.block,
            launch_stack_task=mock_launch_stack_task,
            suspend_user_stack=mock_suspend_user_stack
        ):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertNotEqual(result, mock_result.result)
        self.assertFalse(mock_launch_stack_task.called)
        self.assertTrue(mock_suspend_user_stack.called)

    def test_get_user_stack_status_reset_before_suspend(self):
        self.init_block()

        now = int(time.time())
        suspend_timeout = self.block.configuration.get("suspend_timeout")
        suspend_timestamp = now - suspend_timeout + 1
        self.block.stacks = {
            self.block.stack_name: {
                "suspend_timestamp": suspend_timestamp,
                "status": {"status": "RESUME_COMPLETE"}
            }
        }

        mock_result = Mock()
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task=Mock(return_value=mock_result)
        mock_suspend_user_stack=Mock()

        with patch.multiple(self.block,
            launch_stack_task=mock_launch_stack_task,
            suspend_user_stack=mock_suspend_user_stack
        ):
            data = {
                "initialize": True,
                "reset": True
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, mock_result.result)
        self.assertTrue(mock_launch_stack_task.called)
        self.assertTrue(mock_suspend_user_stack.called)
