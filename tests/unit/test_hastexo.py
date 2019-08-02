import time
import json
import textwrap
from hastexo.models import Stack
from hastexo.hastexo import HastexoXBlock
from hastexo.common import (DEFAULT_SETTINGS, get_stack, update_stack,
                            get_xblock_settings)

from mock import Mock, patch, DEFAULT
from webob import Request
from django.test import TestCase
from django.utils import timezone
from workbench.runtime import WorkbenchRuntime
from xblock.fields import ScopeIds
from xblock.runtime import KvsFieldData, DictKeyValueStore
from xblock.test.test_parsing import XmlTest


def make_request(data, method='POST'):
    """
    Make a webob JSON request

    """
    request = Request.blank('/')
    request.method = 'POST'
    request.body = json.dumps(data).encode('utf-8') if data is not None else ""
    request.method = method
    return request


class TestHastexoXBlockParsing(XmlTest, TestCase):
    def test_parsing_deprecated(self):
        block = self.parse_xml_to_block(textwrap.dedent("""\
    <?xml version='1.0' encoding='utf-8'?>
    <hastexo
      stack_template_path='hot_lab.yaml'
      stack_user_name='training'
      stack_protocol='rdp'
      launch_timeout='900'>
      <provider name='provider1' capacity='20'
        environment='hot_env1.yaml' />
      <provider name='provider2' capacity='30' template='hot_lab2.yaml'
        environment='hot_env2.yaml' />
      <provider name='provider3' capacity='0' template='hot_lab3.yaml'
        environment='hot_env3.yaml' />
      <port name='server1' number='3389' />
      <port name='server2' number='3390' />
      <test>
        Multi-line
        test 1
      </test>
      <test>
        Multi-line
        test 2
      </test>
    </hastexo>
        """).encode('utf-8'))

        self.assertIsInstance(block, HastexoXBlock)
        self.assertEqual(block.stack_template_path, "hot_lab.yaml")
        self.assertEqual(block.stack_user_name, "training")
        self.assertEqual(block.stack_protocol, "rdp")
        self.assertEqual(block.launch_timeout, 900)
        self.assertEqual(len(block.providers), 3)
        self.assertEqual(block.providers[0]["name"], "provider1")
        self.assertEqual(block.providers[0]["template"], None)
        self.assertEqual(block.providers[1]["template"], "hot_lab2.yaml")
        self.assertEqual(block.providers[1]["capacity"], 30)
        self.assertEqual(block.providers[2]["environment"], "hot_env3.yaml")
        self.assertEqual(len(block.ports), 2)
        self.assertEqual(block.ports[0]["number"], 3389)
        self.assertEqual(block.ports[1]["name"], "server2")
        self.assertEqual(len(block.tests), 2)
        self.assertEqual(block.tests[0], "Multi-line\ntest 1\n")
        self.assertEqual(block.tests[1], "Multi-line\ntest 2\n")

    def test_parsing_deprecated_requires_name(self):
        with self.assertRaises(KeyError):
            self.parse_xml_to_block(textwrap.dedent("""\
        <?xml version='1.0' encoding='utf-8'?>
        <hastexo
          stack_user_name='training'>
          <provider capacity='20' environment='hot_env1.yaml' />
        </hastexo>
            """).encode('utf-8'))

    def test_parsing_deprecated_doesnt_require_template(self):
        self.parse_xml_to_block(textwrap.dedent("""\
    <?xml version='1.0' encoding='utf-8'?>
    <hastexo
      stack_user_name='training'>
      <provider name='provider1' capacity='20'
        environment='hot_env1.yaml' />
    </hastexo>
        """).encode('utf-8'))

    def test_parsing_new(self):
        block = self.parse_xml_to_block(textwrap.dedent("""\
    <?xml version='1.0' encoding='utf-8'?>
    <hastexo xmlns:option="http://code.edx.org/xblock/option"
      stack_template_path='hot_lab.yaml'
      stack_user_name='training'
      stack_protocol='rdp'
      launch_timeout='900'>
      <option:providers>
        - name: provider1
          capacity: 20
          template: hot_lab1.yaml
          environment: hot_env1.yaml
        - name: provider2
          capacity: 30
          template: hot_lab2.yaml
          environment: hot_env2.yaml
        - name: provider3
          capacity: 0
          environment: hot_env3.yaml
      </option:providers>
      <option:ports>
        - name: server1
          number: 3389
        - name: server2
          number: 3390
      </option:ports>
      <option:tests>
        - |
          Multi-line
          test 1
        - |
          Multi-line
          test 2
      </option:tests>
    </hastexo>
            """).encode('utf-8'))

        self.assertIsInstance(block, HastexoXBlock)
        self.assertEqual(block.stack_template_path, "hot_lab.yaml")
        self.assertEqual(block.stack_user_name, "training")
        self.assertEqual(block.stack_protocol, "rdp")
        self.assertEqual(block.launch_timeout, 900)
        self.assertEqual(len(block.providers), 3)
        self.assertEqual(block.providers[0]["name"], "provider1")
        self.assertEqual(block.providers[0]["template"], "hot_lab1.yaml")
        self.assertEqual(block.providers[1]["capacity"], 30)
        self.assertEqual(block.providers[2]["environment"], "hot_env3.yaml")
        self.assertEqual(len(block.ports), 2)
        self.assertEqual(block.ports[0]["number"], 3389)
        self.assertEqual(block.ports[1]["name"], "server2")
        self.assertEqual(len(block.tests), 2)
        self.assertEqual(block.tests[0], "Multi-line\ntest 1\n")
        self.assertEqual(block.tests[1], "Multi-line\ntest 2\n")


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
        self.block.launch_timeout = None
        self.block.provider = ""
        self.block.providers = [
            {"name": "provider1",
             "capacity": 1,
             "template": "bogus_content",
             "environment": "bogus_content"},
            {"name": "provider2",
             "capacity": 2,
             "template": "bogus_content",
             "environment": "bogus_content"},
            {"name": "provider3",
             "capacity": 0,
             "template": "bogus_content",
             "environment": "bogus_content"}
        ]
        self.block.ports = [
            {"name": "server1", "number": 3389},
            {"name": "server2", "number": 3390}
        ]
        self.block.tests = ["bogus_test"]

        # Set on student view
        self.block.stack_name = "bogus_stack"

        # Clear database
        Stack.objects.all().delete()

        # Create stack
        course_id, student_id = self.block.get_block_ids()
        stack, _ = Stack.objects.get_or_create(
            student_id=student_id,
            course_id=course_id,
            name=self.block.stack_name)

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

    def test_get_launch_timeout(self):
        self.init_block()
        settings = get_xblock_settings()
        self.assertEqual(self.block.get_launch_timeout(settings),
                         DEFAULT_SETTINGS["launch_timeout"])
        self.block.launch_timeout = 1800
        self.assertEqual(self.block.get_launch_timeout(settings),
                         self.block.launch_timeout)

    def test_get_user_stack_status_fails_if_template_not_provided(self):
        self.init_block()
        self.block.stack_template_path = None

        data = {
            "initialize": True,
            "reset": False
        }
        result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result["status"], "LAUNCH_ERROR")

    def test_get_user_stack_status_fails_if_template_not_found(self):
        self.init_block()
        mock_read_from_contentstore = Mock(
            side_effect=[None]
        )

        with patch.multiple(
                self.block,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result["status"], "LAUNCH_ERROR")

    def test_get_user_stack_status_fails_if_env_file_not_found(self):
        self.init_block()
        mock_read_from_contentstore = Mock(
            side_effect=['bogus_content', None]
        )

        with patch.multiple(
                self.block,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result["status"], "LAUNCH_ERROR")

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
        mock_launch_stack_task.assert_called_with(
            900, {'providers': self.block.providers,
                  'stack_name': self.block.stack_name,
                  'stack_run': '',
                  'port': None,
                  'course_id': 'all',
                  'stack_user_name': self.block.stack_user_name,
                  'student_id': 'user',
                  'protocol': 'ssh',
                  'reset': False})

    def test_get_user_stack_status_with_no_per_provider_template(self):
        self.init_block()
        self.block.providers = [
            {"name": "provider1",
             "capacity": 1,
             "environment": "bogus_content"}
        ]

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "CREATE_COMPLETE"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=("bogus_content"))

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
        mock_launch_stack_task.assert_called_with(
            900, {'providers': [{"name": "provider1",
                                 "capacity": 1,
                                 "template": "bogus_content",
                                 "environment": "bogus_content"}],
                  'stack_name': self.block.stack_name,
                  'stack_run': '',
                  'port': None,
                  'course_id': 'all',
                  'stack_user_name': self.block.stack_user_name,
                  'student_id': 'user',
                  'protocol': 'ssh',
                  'reset': False})

    def test_get_user_stack_status_with_no_templates(self):
        self.init_block()
        self.block.providers = [
            {"name": "provider1",
             "capacity": 1,
             "environment": "bogus_content"}
        ]
        self.block.stack_template_path = ""

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = {"status": "LAUNCH_ERROR"}
        mock_launch_stack_task = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=("bogus_content"))

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": True,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result["status"], mock_result.result["status"])
        mock_launch_stack_task.assert_not_called()

    def test_get_user_stack_status_pending(self):
        self.init_block()

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = False
        mock_launch_stack_task_result = Mock(return_value=mock_result)
        mock_read_from_contentstore = Mock(return_value=('bogus_content'))
        self.update_stack({
            "status": 'LAUNCH_PENDING',
            "launch_task_id": 'bogus_task_id'
        })

        with patch.multiple(
                self.block,
                launch_stack_task_result=mock_launch_stack_task_result,
                read_from_contentstore=mock_read_from_contentstore):
            data = {
                "initialize": False,
                "reset": False
            }
            result = self.call_handler("get_user_stack_status", data)

        self.assertEqual(result, {"status": "LAUNCH_PENDING"})
        self.assertTrue(mock_launch_stack_task_result.called)

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
        mock_result.result = {"status": "LAUNCH_ERROR"}
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

        self.assertEqual(result["status"], mock_result.result["status"])
        self.assertFalse(mock_launch_stack_task.called)

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
