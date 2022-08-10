import time
import logging
import os
import re
import string
import textwrap

from xblock.core import XBlock, XML_NAMESPACES
from xblock.fields import Scope, Float, String, Dict, List, Integer, Boolean
from xblock.fragment import Fragment
from xblock.scorable import ScorableXBlockMixin, Score
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import (
    NestedXBlockSpec,
    StudioContainerWithNestedXBlocksMixin,
    StudioEditableXBlockMixin,
)
from xblockutils.settings import XBlockWithSettingsMixin

from distutils.util import strtobool
from django.db import transaction
from django.utils import timezone
from lxml import etree

from common.djangoapps.student.models import AnonymousUserId

from .models import Stack
from .common import (
    UP_STATES,
    DOWN_STATES,
    PENDING_STATES,
    LAUNCH_PENDING,
    LAUNCH_ERROR,
    SETTINGS_KEY,
    get_xblock_settings,
    get_stack,
    update_stack
)
from .tasks import LaunchStackTask, CheckStudentProgressTask

logger = logging.getLogger(__name__)
loader = ResourceLoader(__name__)


class LaunchError(Exception):
    error_msg = ""

    def __init__(self, error_msg):
        super(LaunchError, self).__init__()

        self.error_msg = textwrap.shorten(error_msg, width=256)


@XBlock.wants('settings')
class HastexoXBlock(XBlock,
                    XBlockWithSettingsMixin,
                    ScorableXBlockMixin,
                    StudioEditableXBlockMixin,
                    StudioContainerWithNestedXBlocksMixin):
    """
    Provides lab environments and an SSH connection to them.

    """
    CATEGORY = "hastexo"
    STUDIO_LABEL = "hastexo XBlock"

    # Settings with defaults.
    display_name = String(
        default="hastexo XBlock",
        scope=Scope.settings,
        help="Title to display")
    weight = Float(
        default=1,
        scope=Scope.settings,
        help="Defines the maximum total grade of the block.")

    # Mandatory: must be set per instance.
    stack_user_name = String(
        scope=Scope.settings,
        help="The name of the training user in the stack.")
    stack_protocol = String(
        values=["ssh", "rdp", "vnc"],
        default="ssh",
        scope=Scope.settings,
        help="What protocol to use for the connection. "
             "Currently, \"ssh\", \"rdp\", or \"vnc\".")

    # Optional
    stack_template_path = String(
        scope=Scope.settings,
        help="The relative path to the uploaded orchestration template. "
             "For example, \"hot_lab.yaml\".")
    launch_timeout = Integer(
        default=None,
        scope=Scope.settings,
        help="Timeout for a launch operation, in seconds.  Takes precedence"
             "over the globally defined timeout.")
    suspend_timeout = Integer(
        default=None,
        scope=Scope.settings,
        help="Timeout for how long to wait before suspending a stack, after "
             "the last keepalive was received from the browser, in seconds. "
             "Takes precedence over the globally defined timeout.")
    hook_script = String(
        scope=Scope.settings,
        help="The relative path to an uploaded executable script. "
             "For example, \"hot_script.sh\".")
    delete_age = String(
        default=None,
        scope=Scope.settings,
        help="Delete stacks that haven't been resumed in this many seconds. "
             "Overrides the globally defined setting."
    )
    read_only = Boolean(
        default=False,
        scope=Scope.settings,
        help="Display the terminal window in read-only mode"
    )
    hidden = Boolean(
        default=False,
        scope=Scope.settings,
        help="Hide the terminal window while running the background tasks. "
    )
    progress_check_label = String(
        default='Check Progress',
        scope=Scope.settings,
        help="Set the progress check button label. "
             "For example: \"Submit Answer\" or \"Check Progress\"(Default)."
    )
    show_feedback = Boolean(
        default=True,
        scope=Scope.settings,
        help="On progress check, show feedback on how many tasks out of total "
             "are completed."
    )
    show_hints_on_error = Boolean(
        default=True,
        scope=Scope.settings,
        help="On progress check failure, display the tests' standard error "
             "streams as hints. When 'show_feedback' is set to False, hints "
             "will never be displayed and setting this to True will have no "
             "effect."
    )
    progress_check_result_heading = String(
        default='Progress check result',
        scope=Scope.settings,
        help="Message to display on progress check result window. This could "
             "be set to \"Answer Submitted\" for example, when choosing to "
             "not display hints and feedback. Default is \"Progress check "
             "result\"."
    )

    # Set via XML
    hook_events = Dict(
        default=None,
        scope=Scope.settings,
        enforce_type=True,
        help="A dictionary of (string, boolean) pairs, where `string` is any "
             "of \"suspend\", \"resume\", and \"delete\".")
    ports = List(
        default=[],
        scope=Scope.settings,
        enforce_type=True,
        help="What ports are available in the stack.")
    providers = List(
        default=[],
        scope=Scope.settings,
        enforce_type=True,
        help="List of providers to launch the stack in.")
    tests = List(
        default=[],
        scope=Scope.content,
        enforce_type=True,
        help="The list of tests to run.")

    # Deprecated in favor of "providers"
    provider = String(
        default="",
        scope=Scope.settings,
        help="Where to launch the stack. (DEPRECATED)")

    # User state, per instance.
    stack_run = String(
        default="",
        scope=Scope.user_state,
        help="The name of the run")
    stack_name = String(
        default="",
        scope=Scope.user_state,
        help="The name of the user's stack")
    stack_provider = String(
        default="",
        scope=Scope.user_state,
        help="The provider selected for the current launch of the stack")
    check_id = String(
        default="",
        scope=Scope.user_state,
        help="The check task id")
    check_timestamp = Integer(
        default=None,
        scope=Scope.user_state,
        help="When the check task was launched")
    check_status = Dict(
        default=None,
        scope=Scope.user_state,
        help="The check status")
    score = Dict(
        default=None,
        scope=Scope.user_state,
        help="Dictionary with the current student score")

    editable_fields = (
        'display_name',
        'progress_check_label',
        'progress_check_result_heading',
        'show_feedback',
        'show_hints_on_error',
        'weight',
        'stack_template_path',
        'hook_script',
        'hook_events',
        'stack_user_name',
        'stack_protocol',
        'launch_timeout',
        'suspend_timeout',
        'delete_age',
        'ports',
        'providers',
        'tests',
        'read_only',
        'hidden')

    has_author_view = True
    has_score = True
    has_children = True
    icon_class = 'problem'
    block_settings_key = SETTINGS_KEY

    def parse_attributes(tag, node, block):
        """
        Handle parsing tests, ports and providers.
        """
        if tag == "test":
            text = node.text

            # Fix up whitespace.
            if text[0] == "\n":
                text = text[1:]
            text.rstrip()
            text = textwrap.dedent(text)

            block.tests.append(text)

        elif tag == "port":
            # port must have values for 'name' and 'number'
            # raises KeyError for each if not defined
            port = {"name": node.attrib["name"],
                    "number": int(node.attrib["number"])}
            block.ports.append(port)

        elif tag == "provider":
            # raises KeyError if 'name' is not defined
            # one must not add a provider without a name
            name = node.attrib["name"]
            capacity = node.attrib.get("capacity", None)
            if capacity in (None, "None", ""):
                # capacity should not be undefined
                # set to -1 (unlimited) in case it is
                capacity = -1
            else:
                # This will raise a TypeError if the string literal
                # cannot be converted
                capacity = int(capacity)
            provider = {"name": name,
                        "capacity": capacity}
            # template and environment are not required
            # add to provider only when they have non empty values
            template = node.attrib.get("template", None)
            if template not in (None, "None"):
                provider["template"] = template
            environment = node.attrib.get("environment", None)
            if environment not in (None, "None"):
                provider["environment"] = environment
            block.providers.append(provider)

    @classmethod
    def parse_xml(cls, node, runtime, keys, id_generator):
        """
        Use `node` to construct a new block.
        """
        block = runtime.construct_xblock_from_class(cls, keys)

        if 'filename' in node.attrib:
            # Read xml content from file.
            url_name = node.get('url_name', node.get('slug'))
            location = id_generator.create_definition(node.tag, url_name)

            filename = node.get('filename')
            pointer_path = "{category}/{url_path}".format(
                category='hastexo',
                url_path=location.block_id.replace(':', '/')
            )
            base = os.path.dirname(pointer_path)
            filepath = u"{base}/{name}.xml".format(base=base, name=filename)

            with runtime.resources_fs.open(
                    filepath, encoding='utf-8') as infile:
                root = etree.fromstring(infile.read())
                for child in root:
                    if child.tag is etree.Comment:
                        continue

                    elif child.tag in ['test', 'port', 'provider']:
                        cls.parse_attributes(child.tag, child, block)

                    elif child.tag == "hook_events":
                        hook_events = {
                            "suspend": bool(strtobool(
                                child.attrib.get("suspend", "true"))),
                            "resume": bool(strtobool(
                                child.attrib.get("resume", "true"))),
                            "delete": bool(strtobool(
                                child.attrib.get("delete", "true")))
                        }
                        block.hook_events = hook_events

                    else:
                        logger.warning(
                            "Attribute unknown to Hastexo XBlock: {}".format(
                                child.tag))
            # Import nested blocks
            for child in node:
                block.runtime.add_node_as_child(block, child, id_generator)
        else:
            for child in node:
                if child.tag is etree.Comment:
                    continue

                qname = etree.QName(child)
                tag = qname.localname
                namespace = qname.namespace

                if namespace == XML_NAMESPACES["option"]:
                    cls._set_field_if_present(
                        block, tag, child.text, child.attrib)
                elif tag in ['test', 'port', 'provider']:
                    cls.parse_attributes(child.tag, child, block)
                else:
                    # Import nested blocks
                    block.runtime.add_node_as_child(block, child, id_generator)

        # Attributes become fields.
        for name, value in list(node.items()):  # lxml has no iteritems
            cls._set_field_if_present(block, name, value, {})

        return block

    def add_xml_to_node(self, node):
        """
        For exporting, set data on etree.Element `node`.
        """

        # Write xml data to file
        pathname = self.url_name.replace(':', '/')
        filepath = u'{category}/{pathname}.xml'.format(
            category=self.category,
            pathname=pathname
        )

        self.runtime.export_fs.makedirs(
            os.path.dirname(filepath),
            recreate=True)

        with self.runtime.export_fs.open(filepath, 'wb') as filestream:
            root = etree.Element('hastexo')

            if self.hook_events:
                hook_events_node = etree.SubElement(root, 'hook_events')
                hook_events_node.set(
                    'suspend', str(self.hook_events.get("suspend", True)))
                hook_events_node.set(
                    'resume', str(self.hook_events.get("resume", True)))
                hook_events_node.set(
                    'delete', str(self.hook_events.get("delete", True)))

            if self.ports:
                for port in self.ports:
                    # port must have values for 'name' and 'number',
                    # raises KeyError if not defined.
                    port_node = etree.SubElement(root, 'port')
                    port_node.set('name', port['name'])
                    port_node.set('number', str(port['number']))

            if self.providers:
                for provider in self.providers:
                    provider_node = etree.SubElement(root, 'provider')
                    # raises KeyError if 'name' is not defined
                    # one must not add a provider without a name
                    provider_node.set('name', provider['name'])
                    capacity = provider.get("capacity", None)
                    if capacity in (None, "None", ""):
                        # capacity should not be undefined
                        # set to -1 (unlimited) in case it is
                        capacity = -1
                    provider_node.set('capacity', str(capacity))
                    # Not having a 'template' or an 'environment' defined for
                    # a provider is a valid option.
                    # Only add to node when defined a non-empty value.
                    template = provider.get("template", None)
                    if template not in (None, "None"):
                        provider_node.set('template', template)
                    environment = provider.get("environment", None)
                    if environment not in (None, "None"):
                        provider_node.set('environment', environment)

            if self.tests:
                for test in self.tests:
                    etree.SubElement(
                        root, 'test').text = etree.CDATA(test)
            etree.ElementTree(
                root).write(filestream, pretty_print=True, encoding='utf-8')

        # Write out the xml file name
        filename = os.path.basename(pathname)

        # Add all editable fields as node attributes
        node.tag = self.category
        node.set("filename", filename)
        node.set('xblock-family', self.entry_point)
        node.set('display_name', self.display_name)
        node.set('progress_check_label', self.progress_check_label)
        node.set('show_hints_on_error', str(self.show_hints_on_error))
        node.set('show_feedback', str(self.show_feedback))
        node.set('progress_check_result_heading',
                 self.progress_check_result_heading)
        node.set('weight', str(self.weight))
        node.set('stack_user_name', self.stack_user_name)
        node.set('stack_protocol', self.stack_protocol)
        node.set('stack_template_path', self.stack_template_path or '')
        node.set('launch_timeout', str(self.launch_timeout or ''))
        node.set('suspend_timeout', str(self.suspend_timeout or ''))
        node.set('hook_script', self.hook_script or '')
        node.set('delete_age', str(self.delete_age or ''))
        node.set('read_only', str(self.read_only))

        # Include nested blocks in course export
        if self.has_children:
            for child_id in self.children:
                child = self.runtime.get_block(child_id)
                self.runtime.add_block_as_child_node(child, node)

    @property
    def allowed_nested_blocks(self):
        """
        Returns a list of allowed nested blocks.

        """
        additional_blocks = []
        try:
            from xmodule.video_module.video_module import VideoBlock
            _spec = NestedXBlockSpec(
                VideoBlock, category="video", label=u"Video"
            )
            additional_blocks.append(_spec)
        except ImportError:
            logger.warning("Unable to import VideoBlock", exc_info=True)

        try:
            from pdf import pdfXBlock
            _spec = NestedXBlockSpec(pdfXBlock, category="pdf", label=u"PDF")
            additional_blocks.append(_spec)
        except ImportError:
            logger.info("Unable to import pdfXblock", exc_info=True)

        try:
            from markdown_xblock import MarkdownXBlock
            _spec = NestedXBlockSpec(MarkdownXBlock,
                                     category="markdown",
                                     label=u"Markdown")
            additional_blocks.append(_spec)
        except ImportError:
            logger.info("Unable to import MarkdownXBlock", exc_info=True)

        return [
            NestedXBlockSpec(None, category="html", label=u"HTML")
        ] + additional_blocks

    def is_correct(self):
        if not (self.check_status and isinstance(self.check_status, dict)):
            return False
        else:
            total = self.check_status.get('total')
            if not total:
                return False
            else:
                score = self.check_status.get('pass')
                return score == total

    def get_block_ids(self):
        try:
            course_id = getattr(self.xmodule_runtime, 'course_id', 'all')
            student_id = self.xmodule_runtime.anonymous_student_id
        except AttributeError:
            course_id = 'all'
            student_id = self.scope_ids.user_id

        return (course_id, student_id)

    def get_launch_timeout(self, settings):
        launch_timeout = None
        if self.launch_timeout:
            launch_timeout = self.launch_timeout
        else:
            launch_timeout = settings.get("launch_timeout")

        return launch_timeout

    def get_delete_age(self, settings):
        """
        Return 'delete_age' in seconds.
        XBlock attribute overrides the global setting.
        """
        if self.delete_age:
            # delete_age attribute value is already in seconds
            return int(self.delete_age)
        else:
            # delete_age value in settings is in days, convert to seconds
            return settings.get("delete_age", 14) * 86400

    def get_suspend_timeout(self):
        """
        Return 'suspend_timeout' in seconds.
        XBlock attribute overrides the global setting.
        """
        if self.suspend_timeout:
            return int(self.suspend_timeout)
        else:
            settings = get_xblock_settings()
            return settings.get("suspend_timeout", 120)

    def get_stack_name(self):
        # Get the course id and anonymous user id, and derive the stack name
        # from them
        course_id, student_id = self.get_block_ids()
        stack_name = "%s_%s_%s" % (course_id.course, course_id.run, student_id)

        # Replace anything in the stack name that is not an ASCII letter or
        # digit with an underscore
        replace_pattern = '[^%s%s]' % (string.digits, string.ascii_letters)
        stack_name = re.sub(re.compile(replace_pattern), '_', stack_name)

        return stack_name

    def student_view(self, context=None):
        """
        The primary view of the HastexoXBlock, shown to students when viewing
        courses.
        """
        # Load configuration
        settings = get_xblock_settings()

        # Get the course id and anonymous user id, and derive the stack name
        # from them
        course_id, student_id = self.get_block_ids()
        self.stack_run = "%s_%s" % (course_id.course, course_id.run)
        self.stack_name = self.get_stack_name()

        frag = Fragment()

        # Render children
        child_content = ""
        for child_id in self.children:
            child = self.runtime.get_block(child_id)
            child_fragment = child.render("student_view", context)
            frag.add_frag_resources(child_fragment)
            child_content += child_fragment.content

        # Render the main template
        frag.add_content(loader.render_django_template(
            "static/html/main.html", {"child_content": child_content}
        ))

        # Add the public CSS and JS
        frag.add_css_url(
            self.runtime.local_resource_url(self, 'public/css/main.css')
        )
        frag.add_javascript_url(
            self.runtime.local_resource_url(self, 'public/js/plugins.js')
        )
        frag.add_javascript_url(
            self.runtime.local_resource_url(self, 'public/js/main.js')
        )
        guac_js_version = settings.get("guacamole_js_version", "1.4.0")
        frag.add_javascript_url(
            self.runtime.local_resource_url(
                self,
                f'public/js/guacamole-common-js/{guac_js_version}-all.min.js')
        )

        # Create the stack in the database
        stack = self.create_stack(settings, course_id, student_id)

        # Call the JS initialization function
        frag.initialize_js('HastexoXBlock', {
            "terminal_url": settings.get("terminal_url"),
            "timeouts": settings.get("js_timeouts"),
            "has_tests": len(self.tests) > 0,
            "protocol": self.stack_protocol,
            "ports": self.ports,
            "port": stack.port,
            "instructions_layout": settings.get("instructions_layout"),
            "read_only": self.read_only or self.hidden,
            "hidden": self.hidden,
            "progress_check_label": self.progress_check_label,
            "show_hints_on_error": self.show_hints_on_error,
            "show_feedback": self.show_feedback,
            "progress_check_result_heading": self.progress_check_result_heading
        })

        return frag

    @transaction.atomic
    def create_stack(self, settings, course_id, student_id):
        # use the 'student_id' to link the stack to user
        learner = AnonymousUserId.objects.get(
            anonymous_user_id=student_id).user

        stack, _ = Stack.objects.select_for_update().get_or_create(
            student_id=student_id,
            course_id=course_id,
            name=self.stack_name,
            learner=learner
        )

        # Set the port
        port = None
        if len(self.ports) > 0:
            ports = [p["number"] for p in self.ports]
            port = stack.port
            if not port or port not in ports:
                port = self.ports[0]["number"]

        # Set the providers
        providers = []
        if len(self.providers):
            for provider in self.providers:
                p = dict(provider)

                if not p.get("template"):
                    p["template"] = self.stack_template_path

                if not p["template"]:
                    raise Exception("Provider [%s] template file not "
                                    "provided for [%s]." %
                                    (p["name"], self.stack_name))
                providers.append(p)
        elif self.provider:
            # For backward compatibility
            if not self.stack_template_path:
                raise Exception("Provider [%s] template file not provided "
                                "for [%s]." % (self.provider,
                                               self.stack_name))

            providers.append({
                "name": self.provider,
                "capacity": -1,
                "template": self.stack_template_path,
                "environment": None
            })
        else:
            # No providers have been configured.  Use the "default" one if
            # it exists, or the first one if not.
            configured_providers = settings.get("providers", {})
            provider_name = None
            if configured_providers.get("default"):
                provider_name = "default"
            else:
                try:
                    provider_name = next(iter(configured_providers))
                except StopIteration:
                    pass

            if not provider_name:
                raise Exception("Provider not configured for [%s]." %
                                self.stack_name)
            elif not self.stack_template_path:
                raise Exception("Provider [%s] template file not "
                                "provided for [%s]." % (provider_name,
                                                        self.stack_name))
            else:
                providers.append({
                    "name": provider_name,
                    "capacity": -1,
                    "template": self.stack_template_path,
                    "environment": None
                })

        # Save
        stack.user = self.stack_user_name
        stack.run = self.stack_run
        stack.hook_script = self.hook_script
        stack.hook_events = self.hook_events
        stack.protocol = self.stack_protocol
        stack.port = port
        stack.providers = providers
        stack.delete_age = self.get_delete_age(settings)

        stack.save(update_fields=[
            "user",
            "run",
            "hook_script",
            "hook_events",
            "protocol",
            "port",
            "providers",
            "delete_age"
        ])

        return stack

    def update_stack(self, data):
        """
        Updates a stack in the database with the given data.  Must be invoked
        in a transaction.
        """
        course_id, student_id = self.get_block_ids()
        if not self.stack_name:
            # Stack name can be occasionally end up being empty (after deleting
            # learners state for example). If so, set it again.
            self.stack_name = self.get_stack_name()
        update_stack(self.stack_name, course_id, student_id, data)

    def get_stack(self, prop=None):
        course_id, student_id = self.get_block_ids()
        return get_stack(self.stack_name, course_id, student_id, prop)

    def launch_stack_task(self, settings, kwargs):
        soft_time_limit = self.get_launch_timeout(settings)
        hard_time_limit = soft_time_limit + 30

        return LaunchStackTask.apply_async(
            kwargs=kwargs,
            expires=soft_time_limit,
            soft_time_limit=soft_time_limit,
            time_limit=hard_time_limit
        )

    def launch_stack_task_result(self, task_id):
        return LaunchStackTask.AsyncResult(task_id)

    @XBlock.json_handler
    @transaction.atomic
    def get_user_stack_status(self, request_data, suffix=''):
        """
        Update the user stack status and return it.

        """
        settings = get_xblock_settings()
        course_id, student_id = self.get_block_ids()
        initialize = request_data.get("initialize", False)
        reset = request_data.get("reset", False)

        stack = Stack.objects.select_for_update().get(
            student_id=student_id,
            course_id=course_id,
            name=self.stack_name
        )

        def _launch_stack(reset=False):
            # Run
            result = self.launch_stack_task(settings, {
                "stack_id": stack.id,
                "reset": reset,
                "learner_id": stack.learner.id
            })

            # Update stack
            stack.status = LAUNCH_PENDING
            stack.error_msg = ""
            stack.launch_task_id = result.id
            stack.launch_timestamp = timezone.now()

            logger.info("Fired async launch task [%s] for [%s]" % (
                result.id, self.stack_name))

            return result

        def _check_result(result):
            if result and result.ready() and not result.successful():
                raise LaunchError(repr(result.result))

        if stack.status in DOWN_STATES or not stack.status:
            # Launch the stack if there's no known status, or if it's known to
            # be down.
            logger.info("Launching stack [%s] with previous status [%s]." %
                        (self.stack_name, stack.status))
            try:
                _check_result(_launch_stack(reset))
            except LaunchError as e:
                stack.status = LAUNCH_ERROR
                stack.error_msg = e.error_msg
        elif stack.status in UP_STATES:
            # The stack is up.  Reset it, if requested.
            if reset:
                logger.info("Resetting successfully launched stack [%s]." %
                            (self.stack_name))
                try:
                    _check_result(_launch_stack(reset))
                except LaunchError as e:
                    stack.status = LAUNCH_ERROR
                    stack.error_msg = e.error_msg

            else:
                logger.info("Successful launch detected for [%s], "
                            "with status [%s]" %
                            (self.stack_name, stack.status))
        elif stack.status == LAUNCH_PENDING:
            # The stack is pending launch.
            try:
                # Check if the Celery task hasn't blown up.
                task_id = stack.launch_task_id
                _check_result(self.launch_stack_task_result(task_id))
            except LaunchError as e:
                stack.status = LAUNCH_ERROR
                stack.error_msg = e.error_msg
            else:
                # Calculate time since launch
                time_since_launch = 0
                launch_timestamp = stack.launch_timestamp
                if launch_timestamp:
                    time_since_launch = (timezone.now() -
                                         launch_timestamp).seconds
                launch_timeout = self.get_launch_timeout(settings)

                # Check if the pending task hasn't timed out.
                if time_since_launch <= launch_timeout:
                    # The pending task still has some time to finish.
                    # Please wait.
                    logger.debug("Launch pending for [%s]" % (self.stack_name))

                elif initialize or reset:
                    # Timeout reached, but the user just entered the page or
                    # requested a reset.  Try launching the stack again.
                    if initialize:
                        logger.info("Launch timeout detected on initialize. "
                                    "Launching stack [%s]" % (self.stack_name))
                    else:
                        logger.info("Launch timeout detected on reset. "
                                    "Resetting stack [%s]" % (self.stack_name))
                    try:
                        _check_result(_launch_stack(reset))
                    except LaunchError as e:
                        stack.status = LAUNCH_ERROR
                        stack.error_msg = e.error_msg
                else:
                    # Timeout reached.  Consider the task a failure and let the
                    # user retry manually.
                    logger.error("Launch timeout reached for [%s] "
                                 "after %s seconds" % (self.stack_name,
                                                       time_since_launch))
                    stack.status = LAUNCH_ERROR
                    stack.error_msg = "Timeout when launching stack."
        elif stack.status in PENDING_STATES:
            # The stack is otherwise pending.  Report and let the user retry
            # manually.
            logger.error("Detected pending stack [%s], "
                         "with status [%s]" % (self.stack_name,
                                               stack.status))
        elif initialize or reset:
            # Detected an unforeseen state, but the user just entered the page,
            # or requested a retry or reset, so start from scratch.
            if reset:
                logger.info("Resetting failed stack [%s]." %
                            (self.stack_name))
            else:
                logger.info("Retrying previously failed stack [%s]." %
                            (self.stack_name))
            try:
                _check_result(_launch_stack(reset))
            except LaunchError as e:
                stack.status = LAUNCH_ERROR
                stack.error_msg = e.error_msg
        else:
            # Detected a failed stack.  Report the error and let the user retry
            # manually.
            logger.error("Failed stack [%s] detected with status [%s]." %
                         (self.stack_name, stack.status))

        # Reset the dead man's switch
        stack.suspend_timestamp = timezone.now()
        stack.suspend_by = timezone.now() + timezone.timedelta(
            seconds=self.get_suspend_timeout()
        )

        # Save changes to the database
        stack.save()

        return {
            "status": stack.status,
            "error_msg": stack.error_msg,
            "name": stack.name
        }

    @XBlock.json_handler
    @transaction.atomic
    def keepalive(self, data, suffix=''):
        """
        Reset the dead man's switch.

        """
        self.update_stack({
            "suspend_timestamp": timezone.now(),
            "suspend_by": timezone.now() + timezone.timedelta(
                seconds=self.get_suspend_timeout())
        })

    @XBlock.json_handler
    @transaction.atomic
    def set_port(self, data, suffix=''):
        """
        Set the preferred stack port

        """
        self.update_stack({"port": int(data.get("port"))})

    def check_progress_task(self, soft_time_limit, **kwargs):
        time_limit = soft_time_limit + 30
        result = CheckStudentProgressTask.apply_async(
            kwargs=kwargs,
            expires=soft_time_limit,
            soft_time_limit=soft_time_limit,
            time_limit=time_limit
        )

        return result

    def check_progress_task_result(self, check_id):
        return CheckStudentProgressTask.AsyncResult(check_id)

    @XBlock.json_handler
    def get_check_status(self, data, suffix=''):
        """
        Checks the current student score.
        """
        settings = get_xblock_settings()
        check_timeout = settings.get("check_timeout")

        def _launch_check():
            stack = self.get_stack()
            logger.info('Executing tests for stack [%s], IP [%s], user [%s]:' %
                        (self.stack_name, stack.ip,
                         self.stack_user_name))
            for test in self.tests:
                logger.info('Test: %s' % test)

            kwargs = {
                "tests": self.tests,
                "stack_ip": stack.ip,
                "stack_user_name": self.stack_user_name,
                "stack_key": stack.key
            }
            result = self.check_progress_task(check_timeout, **kwargs)

            # Save task ID and timestamp
            self.check_id = result.id
            self.check_timestamp = int(time.time())

            return result

        def _process_result(result):
            if result.ready():
                # Clear the task ID so we know there is no task running.
                self.check_id = ""

                if (result.successful() and
                        isinstance(result.result, dict) and not
                        result.result.get('error')):
                    status = result.result
                    score = Score(raw_earned=status['pass'],
                                  raw_possible=status['total'])
                    self.set_score(score)
                    # A publish event is necessary for calculating grades
                    self.publish_grade()

                else:
                    status = {
                        'status': 'ERROR',
                        'error_msg': 'Unexpected result: %s' % repr(result.result)  # noqa: E501
                    }
            else:
                status = {'status': 'CHECK_PROGRESS_PENDING'}

            # Store the result
            self.check_status = status

            return status

        # If a check task is running, return its status.
        if self.check_id:
            logger.info('Check progress task is running: %s' % self.check_id)
            result = self.check_progress_task_result(self.check_id)
            status = _process_result(result)

            if status['status'] == 'CHECK_PROGRESS_PENDING':
                time_since_check = int(time.time()) - self.check_timestamp

                # Check if the pending task hasn't timed out.
                if time_since_check >= check_timeout:
                    # Timeout reached.  Consider the task a failure and let the
                    # user retry manually.
                    logger.error('Check timeout reached for [%s] '
                                 'after %s seconds' % (self.stack_name,
                                                       time_since_check))
                    self.check_id = ""
                    status = {'status': 'ERROR',
                              'error_msg': "Timeout when checking progress."}

        # Otherwise, launch the check task.
        else:
            result = _launch_check()
            status = _process_result(result)

        return status

    def max_score(self):
        """
        Return the maximum possible score for this XBlock.
        """
        return self.weight

    def has_submitted_answer(self):
        """
        Returns True if the problem has been answered by the runtime user.
        """
        return self.score is not None

    def set_score(self, score):
        """
        Persist a score to the XBlock.

        The score is a named tuple with a raw_earned attribute and a
        raw_possible attribute, reflecting the raw earned score and the maximum
        raw score the student could have earned respectively.

        Arguments:
            score: Score(raw_earned=float, raw_possible=float)

        Returns:
            None
        """
        self.score = {
            'raw_earned': score.raw_earned,
            'raw_possible': score.raw_possible
        }

    def get_score(self):
        """
        Return a raw score already persisted on the XBlock.  Should not
        perform new calculations.
        Returns:
            Score(raw_earned=float, raw_possible=float)
        """
        if not self.score:
            logger.warning("No score is earned for this block yet")
        else:
            return Score(
                raw_earned=self.score.get('raw_earned'),
                raw_possible=self.score.get('raw_possible'))

    def calculate_score(self):
        """
        Calculate a new raw score based on the state of the problem.
        This method should not modify the state of the XBlock.
        Returns:
            Score(raw_earned=float, raw_possible=float)
        """
        # Nothing to calculate here
        # This will be called only if self.has_submitted_answer() returns True
        # Just return the stored value
        return self.get_score()

    def publish_grade(self):
        """
        Publish a grade to the runtime.
        """
        score = self.get_score()
        self._publish_grade(score=score)

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("HastexoXBlock",
             """<vertical_demo>
                <hastexo/>
                </vertical_demo>
             """),
        ]
