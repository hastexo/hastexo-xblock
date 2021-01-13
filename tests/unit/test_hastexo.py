import time
import json
import textwrap
from hastexo.models import Stack
from hastexo.hastexo import HastexoXBlock
from hastexo.common import (
    DEFAULT_SETTINGS,
    get_stack,
    update_stack_fields,
    get_xblock_settings
)

from mock import Mock, patch, DEFAULT
from webob import Request
from django.test import TestCase
from workbench.runtime import WorkbenchRuntime
from xblock.core import XBlock
from xblock.fields import ScopeIds
from xblock.runtime import KvsFieldData, DictKeyValueStore
from xblock.test.test_parsing import XmlTest
from sample_xblocks.basic.content import HtmlBlock


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
      <provider name='provider1' capacity='-1' />
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
        self.assertEqual(block.providers[0]["capacity"], -1)
        self.assertNotIn("template", block.providers[0])
        self.assertNotIn("environment", block.providers[0])
        self.assertEqual(block.providers[1]["template"], "hot_lab2.yaml")
        self.assertEqual(block.providers[1]["capacity"], 30)
        self.assertEqual(block.providers[2]["environment"], "hot_env3.yaml")
        self.assertEqual(len(block.ports), 2)
        self.assertEqual(block.ports[0]["number"], 3389)
        self.assertEqual(block.ports[1]["name"], "server2")
        self.assertEqual(len(block.tests), 2)
        self.assertEqual(block.tests[0], "Multi-line\ntest 1\n")
        self.assertEqual(block.tests[1], "Multi-line\ntest 2\n")

    def test_parsing_capacity_empty_values(self):
        block = self.parse_xml_to_block(textwrap.dedent("""\
    <?xml version='1.0' encoding='utf-8'?>
    <hastexo
      stack_template_path='hot_lab.yaml'
      stack_user_name='training'>
      <provider name='provider1'
        environment='hot_env1.yaml' />
      <provider name='provider2' capacity=''
        environment='hot_env2.yaml' />
      <provider name='provider3' capacity='None'
        environment='hot_env3.yaml' />
    </hastexo>
        """).encode('utf-8'))

        self.assertEqual(block.providers[0]["capacity"], -1)
        self.assertEqual(block.providers[1]["capacity"], -1)
        self.assertEqual(block.providers[2]["capacity"], -1)

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

    @XBlock.register_temp_plugin(HtmlBlock, "html")
    def test_student_view(self):
        block = self.parse_xml_to_block(textwrap.dedent("""\
    <?xml version='1.0' encoding='utf-8'?>
    <hastexo xmlns:option="http://code.edx.org/xblock/option"
      stack_template_path='hot_lab.yaml'
      stack_user_name='training'
      stack_protocol='rdp'
      launch_timeout='900'>
      <html>
        This is a child.
      </html>
      <html>
        This is another child.
      </html>
    </hastexo>
            """).encode('utf-8'))

        course_id = Mock(course='course', run='run')
        student_id = 'student'
        mock_get_block_ids = Mock(return_value=(course_id, student_id))
        stack = Mock(port='port')
        mock_create_stack = Mock(return_value=stack)

        with patch.multiple(
                block,
                get_block_ids=mock_get_block_ids,
                create_stack=mock_create_stack):

            frag = block.student_view({})
            html = frag.body_html()

        self.assertIn("This is a child.", html)
        self.assertIn("This is another child.", html)

    @XBlock.register_temp_plugin(HtmlBlock, "html")
    def test_nested_blocks_spec(self):
        """A nested html element should be supported."""
        block = self.parse_xml_to_block(textwrap.dedent("""\
    <?xml version='1.0' encoding='utf-8'?>
    <hastexo xmlns:option="http://code.edx.org/xblock/option"
      stack_template_path='hot_lab.yaml'
      stack_user_name='training'
      stack_protocol='rdp'
      launch_timeout='900'>
      <html>
        This is a child.
      </html>
    </hastexo>
            """).encode('utf-8'))

        specs = block.get_nested_blocks_spec()
        self.assertEqual(len(specs), 2)

    def test_parsing_nested_markdown_xblock(self):
        """A nested markdown element should be supported."""

        with patch('markdown_xblock.html.MarkdownXBlock.parse_xml') as p:
            p.return_value = Mock()

            block = self.parse_xml_to_block(textwrap.dedent("""\
        <?xml version='1.0' encoding='utf-8'?>
        <hastexo xmlns:option="http://code.edx.org/xblock/option"
            stack_template_path='hot_lab.yaml'
            stack_user_name='training'
            stack_protocol='rdp'
            launch_timeout='900'>
            <markdown/>
        </hastexo>
                """).encode('utf-8'))

            self.assertTrue(p.called)
            self.assertTrue(block.has_children)
            nested_blocks = block.get_children()

            self.assertEqual(len(nested_blocks), 1)
            self.assertEqual(nested_blocks[0].display_name, 'Markdown')


class TestHastexoXBlock(TestCase):
    """
    Basic unit tests for the Hastexo XBlock.

    """
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

    def init_block(self, create_stack=True):
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
        if create_stack:
            self.create_stack()

    def create_stack(self):
        course_id, student_id = self.block.get_block_ids()
        settings = get_xblock_settings()
        return self.block.create_stack(settings, course_id, student_id)

    def update_stack(self, data):
        course_id, student_id = self.block.get_block_ids()
        stack = Stack.objects.get(
            student_id=student_id,
            course_id=course_id,
            name=self.block.stack_name
        )
        update_stack_fields(stack, data)
        stack.save(update_fields=list(data.keys()))

    def get_stack(self, prop=None):
        course_id, student_id = self.block.get_block_ids()
        return get_stack(self.block.stack_name, course_id, student_id, prop)

    def call_handler(self,
                     handler_name,
                     data=None,
                     expect_json=True,
                     method='POST'):
        response = self.block.handle(handler_name,
                                     make_request(data, method=method))
        if expect_json:
            self.assertEqual(response.status_code, 200)
            # json.loads() is smart enough to grok both bytes and str
            # from Python 3.6 forward. However in Python 3.5 (Ubuntu
            # Xenial), we must pass json.loads() a str, as it will
            # choke on bytes.
            if isinstance(response.body, bytes):
                return json.loads(response.body.decode('utf-8'))
            else:
                return json.loads(response.body)
        return response

    def test_get_launch_timeout(self):
        self.init_block()
        settings = get_xblock_settings()
        self.assertEqual(self.block.get_launch_timeout(settings),
                         DEFAULT_SETTINGS["launch_timeout"])
        self.block.launch_timeout = 1800
        self.assertEqual(self.block.get_launch_timeout(settings),
                         self.block.launch_timeout)

    def test_create_stack_fails_if_template_not_provided(self):
        self.init_block(False)
        self.block.stack_template_path = None
        self.block.providers[0]["template"] = None
        with self.assertRaises(Exception):
            self.create_stack()

    def test_create_stack_fails_if_fallback_template_not_provided(self):
        self.init_block(False)
        self.block.stack_template_path = None
        self.block.providers = []
        self.block.provider = "bogus"
        with self.assertRaises(Exception):
            self.create_stack()

    def test_create_stack_with_no_per_provider_template(self):
        self.init_block(False)
        self.block.providers = [{
            "name": "provider1",
            "capacity": 1,
            "environment": "bogus_content"
        }]
        self.create_stack()
        stack = self.get_stack()
        self.assertEqual(stack.providers[0]["template"],
                         self.block.stack_template_path)

    def test_create_stack_with_deprecated_provider(self):
        self.init_block(False)
        self.block.providers = []
        self.block.provider = "deprecated"
        self.create_stack()
        stack = self.get_stack()
        self.assertEqual(stack.providers[0]["template"],
                         self.block.stack_template_path)

    def test_create_stack_with_default_provider(self):
        self.init_block(False)
        self.block.providers = []
        providers = {"providers": {"default": {}}}
        with patch.dict(DEFAULT_SETTINGS, providers):
            self.create_stack()
        stack = self.get_stack()
        self.assertEqual(stack.providers[0]["name"], "default")

    def test_create_stack_without_default_provider(self):
        self.init_block(False)
        self.block.providers = []
        providers = {"providers": {"notdefault": {}}}
        with patch.dict(DEFAULT_SETTINGS, providers):
            self.create_stack()
        stack = self.get_stack()
        self.assertEqual(stack.providers[0]["name"], "notdefault")

    def test_create_stack_without_providers(self):
        self.init_block(False)
        self.block.providers = []
        providers = {"providers": {}}
        with patch.dict(DEFAULT_SETTINGS, providers):
            with self.assertRaises(Exception):
                self.create_stack()

    def test_create_stack_with_default_delete_age(self):
        self.init_block(False)
        delete_age = DEFAULT_SETTINGS["delete_age"] * 86400
        self.assertEqual(self.block.delete_age, None)
        self.create_stack()
        stack = self.get_stack()
        self.assertEqual(stack.delete_age, delete_age)

    def test_create_stack_override_default_delete_age(self):
        self.init_block(False)
        delete_age = 3600
        self.block.delete_age = delete_age
        self.create_stack()
        stack = self.get_stack()
        self.assertEqual(stack.delete_age, delete_age)

    def test_get_user_stack_status_first(self):
        self.init_block(False)
        stack = self.create_stack()

        mock_result = Mock()
        mock_result.id = "bogus_task_id"
        mock_result.ready.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        mock_launch_stack_task.assert_called_with(
            get_xblock_settings(),
            {"stack_id": stack.id, "reset": False}
        )
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_resume(self):
        self.init_block()
        self.update_stack({"status": "SUSPEND_COMPLETE"})

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_delete(self):
        self.init_block()
        self.update_stack({"status": "DELETE_COMPLETE"})

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_launch_failure(self):
        self.init_block()

        mock_result = Mock()
        mock_result.id = "bogus_task_id"
        mock_result.ready.return_value = True
        mock_result.successful.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_ERROR")

    def test_get_user_stack_status_up(self):
        # Initialize block
        self.init_block()
        self.update_stack({"status": "CREATE_COMPLETE"})

        # Async result mock
        mock_launch_stack_task = Mock()

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertFalse(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "CREATE_COMPLETE")

    def test_get_user_stack_status_up_reset(self):
        self.init_block()
        self.update_stack({"status": "RESUME_COMPLETE"})

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": True
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_up_reset_failure(self):
        self.init_block()
        self.update_stack({"status": "RESUME_COMPLETE"})

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": True
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_ERROR")

    def test_get_user_stack_status_launch_pending(self):
        self.init_block()
        self.update_stack({
            "status": "LAUNCH_PENDING",
            "launch_task_id": "bogus_task_id"
        })

        mock_result = Mock()
        mock_result.id = "bogus_task_id"
        mock_result.ready.return_value = False
        mock_launch_stack_task_result = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task_result=mock_launch_stack_task_result):
            data = {
                "initialize": False,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task_result.called)
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_launch_pending_failure(self):
        self.init_block()
        self.update_stack({
            "status": "LAUNCH_PENDING",
            "launch_task_id": "bogus_task_id"
        })

        mock_result = Mock()
        mock_result.id = "bogus_task_id"
        mock_result.ready.return_value = True
        mock_result.successful.return_value = False
        mock_launch_stack_task_result = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task_result=mock_launch_stack_task_result):
            data = {
                "initialize": False,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task_result.called)
        self.assertEqual(response["status"], "LAUNCH_ERROR")

    def test_get_user_stack_status_launch_pending_timeout(self):
        self.init_block()
        self.update_stack({
            "status": "LAUNCH_PENDING",
            "launch_task_id": "bogus_task_id"
        })

        mock_result = Mock()
        mock_result.id = "bogus_task_id"
        mock_result.ready.return_value = False
        mock_launch_stack_task_result = Mock(return_value=mock_result)

        self.block.launch_timeout = -1
        with patch.multiple(
                self.block,
                launch_stack_task_result=mock_launch_stack_task_result):
            data = {
                "initialize": False,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task_result.called)
        self.assertEqual(response["status"], "LAUNCH_ERROR")

    def test_get_user_stack_status_launch_pending_timeout_initialize(self):
        self.init_block()
        self.update_stack({
            "status": "LAUNCH_PENDING",
            "launch_task_id": "bogus_task_id"
        })

        mock_result = Mock()
        mock_result.id = "bogus_task_id"
        mock_result.ready.return_value = False
        mock_launch_stack_task_result = Mock(return_value=mock_result)
        mock_launch_stack_task = Mock(return_value=mock_result)

        self.block.launch_timeout = -1
        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                launch_stack_task_result=mock_launch_stack_task_result):
            data = {
                "initialize": True,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task_result.called)
        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_launch_pending_timeout_reset(self):
        self.init_block()
        self.update_stack({
            "status": "LAUNCH_PENDING",
            "launch_task_id": "bogus_task_id"
        })

        mock_result = Mock()
        mock_result.id = "bogus_task_id"
        mock_result.ready.return_value = False
        mock_launch_stack_task_result = Mock(return_value=mock_result)
        mock_launch_stack_task = Mock(return_value=mock_result)

        self.block.launch_timeout = -1
        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                launch_stack_task_result=mock_launch_stack_task_result):
            data = {
                "initialize": False,
                "reset": True
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task_result.called)
        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_launch_pending_timeout_reset_failure(self):
        self.init_block()
        self.update_stack({
            "status": "LAUNCH_PENDING",
            "launch_task_id": "bogus_task_id"
        })

        mock_result = Mock()
        mock_result.id = "bogus_task_id"
        mock_result.ready.side_effect = [False, True]
        mock_result.successful.return_value = False
        mock_launch_stack_task_result = Mock(return_value=mock_result)
        mock_launch_stack_task = Mock(return_value=mock_result)

        self.block.launch_timeout = -1
        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task,
                launch_stack_task_result=mock_launch_stack_task_result):
            data = {
                "initialize": False,
                "reset": True
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task_result.called)
        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_ERROR")

    def test_get_user_stack_status_pending(self):
        self.init_block()
        self.update_stack({"status": "SUSPEND_PENDING"})
        mock_launch_stack_task = Mock()

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": True
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertFalse(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "SUSPEND_PENDING")

    def test_get_user_stack_status_initialize(self):
        self.init_block()
        self.update_stack({"status": "RESUME_FAILED"})

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_reset(self):
        self.init_block()
        self.update_stack({"status": "RESUME_FAILED"})

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": False,
                "reset": True
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_PENDING")

    def test_get_user_stack_status_reset_failure(self):
        self.init_block()
        self.update_stack({"status": "RESUME_FAILED"})

        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = False
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": True,
                "reset": True
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_ERROR")

    def test_get_user_stack_status_failure(self):
        self.init_block()
        self.update_stack({"status": "RESUME_FAILED"})
        mock_launch_stack_task = Mock()

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            data = {
                "initialize": False,
                "reset": False
            }
            response = self.call_handler("get_user_stack_status", data)

        self.assertFalse(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "RESUME_FAILED")

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
