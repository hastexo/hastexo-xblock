import time
import json
import textwrap
import pkg_resources
import os

from hastexo.models import Stack
from hastexo.hastexo import HastexoXBlock
from hastexo.common import (
    DEFAULT_SETTINGS,
    get_stack,
    update_stack_fields,
    get_xblock_settings
)

from common.djangoapps.student.models import AnonymousUserId
from fs.osfs import OSFS
from lxml import etree
from markdown_xblock import MarkdownXBlock
from mock import Mock, patch, DEFAULT
from webob import Request
from django.contrib.auth.models import User
from django.test import TestCase
from workbench.runtime import WorkbenchRuntime
from xblock.core import XBlock
from xblock.fields import ScopeIds
from xblock.runtime import KvsFieldData, DictKeyValueStore
from xblock.scorable import Score
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


class TestHastexoXBlockHTML(TestCase):
    """
    Basic lint/validation checks for the static content bundled with
    the XBlock.

    """

    def test_static(self):
        static_files = ['main.html']
        for static_file in static_files:
            source = pkg_resources.resource_stream(
                'hastexo',
                os.path.join('static', 'html', static_file)
            )
            etree.parse(source,
                        etree.HTMLParser(recover=False))


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
        self.block.hook_events = {
            "suspend": True,
            "resume": True,
            "delete": True
        }
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
        user = User.objects.create_user(
            "fake_user",
            "user@example.com",
            "password"
        )
        AnonymousUserId.objects.create(
            user=user,
            anonymous_user_id=student_id)

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
            {"stack_id": stack.id,
             "reset": False,
             "learner_id": stack.learner.id}
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

    def test_get_user_stack_status_long_error_message(self):
        self.init_block()
        self.update_stack({"status": "SUSPEND_COMPLETE"})

        long_error_message = (
            "Lorem ipsum dolor sit amet, consectetuer adipiscing elit. "
            "Aenean commodo ligula eget dolor. Aenean massa. Cum sociis"
            "natoque penatibus et magnis dis parturient montes, "
            "nascetur ridiculus mus. Donec quam felis, ultricies nec, "
            "pellentesque eu, pretium quis, sem. Nulla consequat massa "
            "quis enim. Donec pede justo, fringilla ve. ")
        mock_result = Mock()
        mock_result.id = 'bogus_task_id'
        mock_result.ready.return_value = True
        mock_result.successful.return_value = False
        mock_result.result = long_error_message
        mock_launch_stack_task = Mock(return_value=mock_result)

        with patch.multiple(
                self.block,
                launch_stack_task=mock_launch_stack_task):
            response = self.call_handler("get_user_stack_status", {})

        self.assertTrue(mock_launch_stack_task.called)
        self.assertEqual(response["status"], "LAUNCH_ERROR")
        # assert that the full error message was not set to the
        # error_msg field.
        self.assertNotEqual(response["error_msg"], long_error_message)
        # assert that the error message was shortened to fit 256 characters
        self.assertTrue(len(response["error_msg"]) <= 256)
        self.assertIn('[...]', response["error_msg"])

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
                    {'value': 1, 'max_value': 1, 'only_if_higher': None}
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

    def test_set_score(self):
        self.init_block()
        self.assertEqual(self.block.score, None)

        new_score = {
            'raw_earned': 2,
            'raw_possible': 3
        }

        self.block.set_score(Score(
            raw_earned=new_score['raw_earned'],
            raw_possible=new_score['raw_possible']
        ))
        self.assertEqual(self.block.score, new_score)

    def test_max_score(self):
        self.init_block()

        max_score = self.block.max_score()
        self.assertEqual(self.block.weight, max_score)

    def test_keepalive(self):
        self.init_block()
        self.call_handler("keepalive", data={})

    def test_get_stack_name_on_update(self):
        self.init_block()
        stack_name = self.block.stack_name
        self.block.stack_name = None
        self.assertIsNone(self.block.stack_name)

        self.block.get_stack_name = Mock()
        self.block.get_stack_name.return_value = stack_name

        self.block.update_stack(data={})
        self.block.get_stack_name.assert_called()
        self.assertIsNotNone(self.block.stack_name)
        self.assertEqual(self.block.stack_name, stack_name)

    def test_get_stack_name(self):
        course_id = Mock(course='course', run='run')
        student_id = 'student'
        self.block.get_block_ids = Mock(return_value=(course_id, student_id))
        stack_name = self.block.get_stack_name()
        self.assertEqual('course_run_student', stack_name)

    def test_get_suspend_timeout(self):
        self.init_block()
        self.assertEqual(self.block.get_suspend_timeout(),
                         DEFAULT_SETTINGS["suspend_timeout"])
        self.block.suspend_timeout = 1800
        self.assertEqual(self.block.get_suspend_timeout(),
                         self.block.suspend_timeout)

    def test_get_stack_name_replace_characters(self):
        course_id = Mock(course='course.name', run='run')
        student_id = 'student'
        self.block.get_block_ids = Mock(return_value=(course_id, student_id))
        stack_name = self.block.get_stack_name()
        self.assertEqual('course_name_run_student', stack_name)

    def test_xblock_export_to_separate_file(self):
        # setup
        self.init_block()
        self.block.url_name = 'fake_lab'
        self.block.category = 'hastexo'
        export_fs = OSFS('fake/course')
        self.block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')
        # assert that the node is empty, with a tag 'unknown'
        self.assertEqual(node.items(), [])
        self.assertEqual(node.tag, 'unknown')

        # run the export
        self.block.add_xml_to_node(node)

        # assert that the node now contains the xblock information
        self.assertNotEqual(node.items(), [])
        self.assertEqual(node.tag, 'hastexo')
        self.assertEqual(node.get('filename'), 'fake_lab')

        # assert that the exported file exists
        self.assertTrue(export_fs.exists('hastexo/fake_lab.xml'))
        export_content = export_fs.readtext('hastexo/fake_lab.xml')
        expected_content = textwrap.dedent("""\
    <hastexo>
      <hook_events suspend="True" resume="True" delete="True"/>
      <port name="server1" number="3389"/>
      <port name="server2" number="3390"/>
      <provider name="provider1" capacity="1" template="bogus_content" environment="bogus_content"/>
      <provider name="provider2" capacity="2" template="bogus_content" environment="bogus_content"/>
      <provider name="provider3" capacity="0" template="bogus_content" environment="bogus_content"/>
      <test><![CDATA[bogus_test]]></test>
    </hastexo>
        """) # noqa

        # assert that the exported file content is as expected
        self.assertEqual(export_content, expected_content)

        # clean up
        export_fs.remove('hastexo/fake_lab.xml')
        export_fs.removedir('hastexo')

    def test_export_to_separate_file_no_provider_name(self):
        # setup
        self.init_block()
        self.block.providers[0].pop('name')
        self.block.url_name = 'fake_lab'
        self.block.category = 'hastexo'
        export_fs = OSFS('fake/course')
        self.block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')

        # assert that missing provider name raises KeyError
        with self.assertRaises(KeyError):
            self.block.add_xml_to_node(node)

    def test_export_to_separate_file_no_port_name(self):
        # setup
        self.init_block()
        self.block.ports[0].pop('name')
        self.block.url_name = 'fake_lab'
        self.block.category = 'hastexo'
        export_fs = OSFS('fake/course')
        self.block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')

        # assert that missing port name raises KeyError
        with self.assertRaises(KeyError):
            self.block.add_xml_to_node(node)

    def test_export_to_separate_file_no_port_number(self):
        # setup
        self.init_block()
        self.block.ports[0].pop('number')
        self.block.url_name = 'fake_lab'
        self.block.category = 'hastexo'
        export_fs = OSFS('fake/course')
        self.block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')

        # assert that missing port number raises KeyError
        with self.assertRaises(KeyError):
            self.block.add_xml_to_node(node)

    def test_xblock_export_no_provider_capacity(self):
        # setup
        self.init_block()
        self.block.providers[0].pop('capacity')
        self.block.url_name = 'fake_lab'
        self.block.category = 'hastexo'
        export_fs = OSFS('fake/course')
        self.block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')

        # run the export
        self.block.add_xml_to_node(node)

        # assert that the exported file exists
        self.assertTrue(export_fs.exists('hastexo/fake_lab.xml'))
        export_content = export_fs.readtext('hastexo/fake_lab.xml')
        expected_content = textwrap.dedent("""\
    <hastexo>
      <hook_events suspend="True" resume="True" delete="True"/>
      <port name="server1" number="3389"/>
      <port name="server2" number="3390"/>
      <provider name="provider1" capacity="-1" template="bogus_content" environment="bogus_content"/>
      <provider name="provider2" capacity="2" template="bogus_content" environment="bogus_content"/>
      <provider name="provider3" capacity="0" template="bogus_content" environment="bogus_content"/>
      <test><![CDATA[bogus_test]]></test>
    </hastexo>
        """) # noqa

        # assert that the exported file content is as expected and a missing
        # provider capacity value will be set to "-1" (unlimited)
        self.assertEqual(export_content, expected_content)

        # clean up
        export_fs.remove('hastexo/fake_lab.xml')
        export_fs.removedir('hastexo')

    def test_export_nested_xblock(self):
        # set up a markdown xblock
        markdown_xblock = MarkdownXBlock(
            self.block.runtime,
            scope_ids=(ScopeIds('user', 'markdown', '.markdown.d0',
                                '.markdown.d0.u0')))
        markdown_xblock.url_name = 'fake_lab_instructions'
        markdown_xblock.category = 'markdown'

        # setup
        self.init_block()
        self.block.children.append(markdown_xblock)
        self.block.url_name = 'fake_lab'
        self.block.category = 'hastexo'
        export_fs = OSFS('fake/course')
        self.block.runtime.export_fs = export_fs
        self.block.runtime.get_block = Mock()
        self.block.runtime.get_block.return_value = markdown_xblock
        self.block.runtime.add_block_as_child_node = Mock()

        # create an empty node
        node = etree.Element('unknown')

        # run the export
        self.block.add_xml_to_node(node)

        # assert get_block and add_block_as_child_node were called
        self.block.runtime.get_block.assert_called_once_with(markdown_xblock)
        self.block.runtime.add_block_as_child_node.assert_called_once_with(
            markdown_xblock, node)

        # assert that the exported file exists
        self.assertTrue(export_fs.exists('hastexo/fake_lab.xml'))

        # clean up
        export_fs.remove('hastexo/fake_lab.xml')
        export_fs.removedir('hastexo')

    def test_parse_xblock_from_separate_file(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('filename', 'fake_lab_1')

        self.block.runtime.resources_fs = OSFS('tests/resources/course')
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)
        scope_ids = ScopeIds('user', block_type, def_id, usage_id)

        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_1'
        id_generator.create_definition.return_value = fake_location

        # run
        block = self.block.parse_xml(
            node, self.block.runtime, scope_ids, id_generator)

        # assertions
        self.assertIsInstance(block, HastexoXBlock)
        self.assertEqual(len(block.providers), 3)
        self.assertEqual(block.providers[0]["name"], "provider1")
        self.assertEqual(block.providers[0]["capacity"], 1)
        self.assertEqual(block.providers[0]["template"], "bogus_content")
        self.assertEqual(block.providers[0]["environment"], "bogus_content")
        self.assertEqual(block.providers[1]["template"], "bogus_content")
        self.assertEqual(block.providers[1]["capacity"], 2)
        self.assertEqual(block.providers[2]["name"], "provider3")
        self.assertEqual(block.providers[2]["capacity"], 0)
        self.assertEqual(len(block.ports), 2)
        self.assertEqual(block.ports[0]["number"], 3389)
        self.assertEqual(block.ports[1]["name"], "server2")
        self.assertEqual(len(block.tests), 1)
        self.assertEqual(block.tests[0], "bogus_test")
        self.assertEqual(
            block.hook_events,
            {"suspend": True, "resume": True, "delete": True})

    def test_parse_xblock_no_filename(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('read_only', 'true')
        node.set('display_name', 'Fake Lab')

        self.block.runtime.resources_fs = Mock()
        id_generator = Mock()
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)
        scope_ids = ScopeIds('user', block_type, def_id, usage_id)

        block = self.block.parse_xml(
            node, self.block.runtime, scope_ids, id_generator)

        # assert that since no 'filename' attribute is present,
        # we don't attempt to open any files.
        self.block.runtime.resources_fs.assert_not_called()

        # assert that the imported xblock has no hook_events,
        # ports, providers or tests.
        self.assertEqual(block.hook_events, None)
        self.assertEqual(block.ports, [])
        self.assertEqual(block.providers, [])
        self.assertEqual(block.tests, [])

        # assert that node attributes are still imported as xblock fields.
        self.assertEqual(block.read_only, True)
        self.assertEqual(block.display_name, 'Fake Lab')

        # assert that default values are present
        self.assertEqual(block.progress_check_label, 'Check Progress')
        self.assertEqual(block.stack_protocol, 'ssh')

    def test_parse_xblock_missing_capacity(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('filename', 'fake_lab_no_provider_capacity')

        self.block.runtime.resources_fs = OSFS('tests/resources/course')
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)

        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_no_provider_capacity'
        id_generator.create_definition.return_value = fake_location

        scope_ids = ScopeIds('user', block_type, def_id, usage_id)
        block = self.block.parse_xml(
            node, self.block.runtime, scope_ids, id_generator)

        # assert that a missing capacity will result on it being set to -1
        self.assertEqual(len(block.providers), 3)
        self.assertEqual(block.providers[0]['capacity'], -1)
        self.assertEqual(block.providers[1]['capacity'], -1)
        self.assertEqual(block.providers[2]['capacity'], -1)

    def test_parse_xblock_missing_provider_name(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('filename', 'fake_lab_no_provider_name')

        self.block.runtime.resources_fs = OSFS('tests/resources/course')
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)

        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_no_provider_name'
        id_generator.create_definition.return_value = fake_location

        scope_ids = ScopeIds('user', block_type, def_id, usage_id)

        # assert that missing provider name raises KeyError
        with self.assertRaises(KeyError):
            self.block.parse_xml(
                node, self.block.runtime, scope_ids, id_generator)

    def test_parse_xblock_missing_port_name(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('filename', 'fake_lab_no_port_name')

        self.block.runtime.resources_fs = OSFS('tests/resources/course')
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)

        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_no_port_name'
        id_generator.create_definition.return_value = fake_location

        scope_ids = ScopeIds('user', block_type, def_id, usage_id)

        # assert that missing port name raises KeyError
        with self.assertRaises(KeyError):
            self.block.parse_xml(
                node, self.block.runtime, scope_ids, id_generator)

    def test_parse_xblock_missing_port_number(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('filename', 'fake_lab_no_port_number')

        self.block.runtime.resources_fs = OSFS('tests/resources/course')
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)

        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_no_port_number'
        id_generator.create_definition.return_value = fake_location

        scope_ids = ScopeIds('user', block_type, def_id, usage_id)

        # assert that missing port number raises KeyError
        with self.assertRaises(KeyError):
            self.block.parse_xml(
                node, self.block.runtime, scope_ids, id_generator)

    def test_parse_xblock_hook_events_1(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('filename', 'fake_lab_hook_events_1')

        self.block.runtime.resources_fs = OSFS('tests/resources/course')
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)

        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_hook_events_1'
        id_generator.create_definition.return_value = fake_location

        scope_ids = ScopeIds('user', block_type, def_id, usage_id)
        block = self.block.parse_xml(
            node, self.block.runtime, scope_ids, id_generator)

        # assert that all three definitions will result in being set to True
        self.assertEqual(block.hook_events['suspend'], True)
        self.assertEqual(block.hook_events['resume'], True)
        self.assertEqual(block.hook_events['delete'], True)

    def test_parse_xblock_hook_events_2(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('filename', 'fake_lab_hook_events_2')

        self.block.runtime.resources_fs = OSFS('tests/resources/course')
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)

        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_hook_events_2'
        id_generator.create_definition.return_value = fake_location

        scope_ids = ScopeIds('user', block_type, def_id, usage_id)
        block = self.block.parse_xml(
            node, self.block.runtime, scope_ids, id_generator)

        # assert that 'false' and 'False' will both be set as False,
        # an undefined attribute ('delete') will default to True
        self.assertEqual(block.hook_events['suspend'], False)
        self.assertEqual(block.hook_events['resume'], False)
        self.assertEqual(block.hook_events['delete'], True)

    def test_parse_xblock_lab_2(self):
        block_type = 'hastexo'

        node = etree.Element(block_type)
        node.set('filename', 'fake_lab_2')

        self.block.runtime.resources_fs = OSFS('tests/resources/course')
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)
        scope_ids = ScopeIds('user', block_type, def_id, usage_id)

        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_2'
        id_generator.create_definition.return_value = fake_location

        # run
        block = self.block.parse_xml(
            node, self.block.runtime, scope_ids, id_generator)

        # assertions
        self.assertIsInstance(block, HastexoXBlock)
        self.assertEqual(len(block.providers), 2)
        self.assertEqual(block.providers[0]["name"], "provider1")
        self.assertEqual(block.providers[0]["capacity"], 1)
        self.assertEqual(block.providers[0]["template"], "bogus_content")
        self.assertEqual(block.providers[0]["environment"], "bogus_content")
        self.assertEqual(block.providers[1]["name"], "provider2")
        self.assertEqual(block.providers[1]["capacity"], 10)
        self.assertEqual(len(block.ports), 1)
        self.assertEqual(block.ports[0]["number"], 3389)
        self.assertEqual(block.ports[0]["name"], "server1")
        self.assertEqual(block.tests[0], "bogus_test")
        self.assertEqual(block.tests[0], "bogus_test")

        # assert that template and environment are not mandatory
        self.assertNotIn("template", block.providers[1])
        self.assertNotIn("environment", block.providers[1])

    def test_full_round_import_export(self):
        # import xblock from fake_lab_1.xml
        # setup
        block_type = 'hastexo'
        resources_fs = OSFS('tests/resources/course')
        self.block.runtime.resources_fs = resources_fs
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)
        scope_ids = ScopeIds('user', block_type, def_id, usage_id)
        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_1'
        id_generator.create_definition.return_value = fake_location

        # create the hastexo node
        hastexo_node = etree.Element(block_type)
        hastexo_node.set('filename', 'fake_lab_1')
        hastexo_node.set('stack_user_name', 'training')

        # run the import
        block = self.block.parse_xml(
            hastexo_node, self.block.runtime, scope_ids, id_generator)

        # export the xblock to fake_lab.xml
        # setup
        block.url_name = 'fake_lab'
        block.category = 'hastexo'
        export_fs = OSFS('fake/course')
        block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')

        # run the export
        block.add_xml_to_node(node)

        # assert that the node has the stack_user_name attribute set on import
        self.assertEqual(node.get('stack_user_name'), 'training')

        # read the exported file content
        export_content = export_fs.readtext('hastexo/fake_lab.xml')
        # read the imported file content
        resource_content = resources_fs.readtext(
            'hastexo/fake_lab_1.xml')

        # assert that exported content is identical to what was imported
        self.assertEqual(
            textwrap.dedent(export_content),
            textwrap.dedent(resource_content))

        # clean up
        export_fs.remove('hastexo/fake_lab.xml')
        export_fs.removedir('hastexo')

    def test_full_round_import_export_2(self):
        # import xblock from fake_lab_2.xml
        # setup
        block_type = 'hastexo'
        resources_fs = OSFS('tests/resources/course')
        self.block.runtime.resources_fs = resources_fs
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)
        scope_ids = ScopeIds('user', block_type, def_id, usage_id)
        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_2'
        id_generator.create_definition.return_value = fake_location

        # create the hastexo node
        hastexo_node = etree.Element(block_type)
        hastexo_node.set('filename', 'fake_lab_2')
        hastexo_node.set('stack_user_name', 'training')

        # run the import
        block = self.block.parse_xml(
            hastexo_node, self.block.runtime, scope_ids, id_generator)

        # export the xblock to fake_lab.xml
        # setup
        block.url_name = 'fake_lab'
        block.category = 'hastexo'
        export_fs = OSFS('fake/course')
        block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')

        # run the export
        block.add_xml_to_node(node)

        # assert that the node has the stack_user_name attribute set on import
        self.assertEqual(node.get('stack_user_name'), 'training')

        # read the exported file content
        export_content = export_fs.readtext('hastexo/fake_lab.xml')
        # read the imported file content
        resource_content = resources_fs.readtext(
            'hastexo/fake_lab_2.xml')

        # assert that exported content is identical to what was imported
        self.assertEqual(
            textwrap.dedent(export_content),
            textwrap.dedent(resource_content))

        # clean up
        export_fs.remove('hastexo/fake_lab.xml')
        export_fs.removedir('hastexo')

    def test_export_import_export(self):
        # Test that two exported files are identical
        # if the same file is imported (while unmodified)
        # before the second export.

        export_location = 'fake/course'

        # set up an xblock and export to fake_lab_1.xml
        self.init_block()
        self.block.url_name = 'fake_lab_1'
        self.block.category = 'hastexo'
        export_fs = OSFS(export_location)
        self.block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')
        # assert that the node is empty, with a tag 'unknown'
        self.assertEqual(node.items(), [])
        self.assertEqual(node.tag, 'unknown')

        # run the export
        self.block.add_xml_to_node(node)

        # assert that the exported file exists and read the content
        self.assertTrue(export_fs.exists('hastexo/fake_lab_1.xml'))
        export_content_1 = export_fs.readtext('hastexo/fake_lab_1.xml')

        # import the exported file from export location
        block_type = 'hastexo'
        resources_fs = OSFS(export_location)
        self.block.runtime.resources_fs = resources_fs
        def_id = self.block.runtime.id_generator.create_definition(block_type)
        usage_id = self.block.runtime.id_generator.create_usage(def_id)
        scope_ids = ScopeIds('user', block_type, def_id, usage_id)
        id_generator = Mock()
        id_generator.create_definition = Mock()
        fake_location = Mock()
        fake_location.block_id = 'fake_lab_1'
        id_generator.create_definition.return_value = fake_location

        # create the hastexo node
        hastexo_node = etree.Element(block_type)
        hastexo_node.set('filename', 'fake_lab_1')
        hastexo_node.set('stack_user_name', 'training')

        # run the import
        block = self.block.parse_xml(
            hastexo_node, self.block.runtime, scope_ids, id_generator)

        # export the imported xblock to fake_lab_2.xml
        block.url_name = 'fake_lab_2'
        block.category = 'hastexo'
        export_fs = OSFS(export_location)
        block.runtime.export_fs = export_fs

        # create an empty node
        node = etree.Element('unknown')

        # run the export
        block.add_xml_to_node(node)

        # assert that the exported file exists and read the content
        self.assertTrue(export_fs.exists('hastexo/fake_lab_2.xml'))
        export_content_2 = export_fs.readtext('hastexo/fake_lab_2.xml')

        # assert that the content of both exported files is identical
        self.assertEqual(
            textwrap.dedent(export_content_1),
            textwrap.dedent(export_content_2))

        # clean up
        export_fs.remove('hastexo/fake_lab_1.xml')
        export_fs.remove('hastexo/fake_lab_2.xml')
        export_fs.removedir('hastexo')
