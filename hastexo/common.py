import errno
import sys
import time
import uuid
import paramiko
import logging
import six

from io import StringIO
from socket import timeout as SocketTimeout
from paramiko.ssh_exception import (AuthenticationException,
                                    SSHException,
                                    NoValidConnectionsError)
from django.conf import settings as django_settings
from pymongo.errors import PyMongoError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from .models import Stack


logger = logging.getLogger(__name__)

ACTIONS = (
    ADOPT,
    CHECK,
    CREATE,
    DELETE,
    LAUNCH,
    RESTORE,
    RESUME,
    ROLLBACK,
    SNAPSHOT,
    SUSPEND,
    UPDATE
) = (
    'ADOPT',
    'CHECK',
    'CREATE',
    'DELETE',
    'LAUNCH',
    'RESTORE',
    'RESUME',
    'ROLLBACK',
    'SNAPSHOT',
    'SUSPEND',
    'UPDATE'
)

STATUSES = (
    COMPLETE,
    ERROR,
    FAILED,
    IN_PROGRESS,
    ISSUED,
    PENDING,
    RETRY,
    TIMEOUT
) = (
    'COMPLETE',
    'ERROR',
    'FAILED',
    'IN_PROGRESS',
    'ISSUED',
    'PENDING',
    'RETRY',
    'TIMEOUT'
)

# Dynamically define all possible states as attributes in this module.  To
# prevent flake8 from complaining about undefined attributes, we add noqa: F821
# where necessary, below.
ALL_STATES = tuple(['%s_%s' % (a, s) for a in ACTIONS for s in STATUSES])
module = sys.modules[__name__]
for state in ALL_STATES:
    setattr(module, state, state)

VALID_STATES = (
    ADOPT_COMPLETE,  # noqa: F821
    ADOPT_FAILED,  # noqa: F821
    ADOPT_IN_PROGRESS,  # noqa: F821
    CHECK_COMPLETE,  # noqa: F821
    CHECK_FAILED,  # noqa: F821
    CHECK_IN_PROGRESS,  # noqa: F821
    CREATE_COMPLETE,  # noqa: F821
    CREATE_FAILED,  # noqa: F821
    CREATE_IN_PROGRESS,  # noqa: F821
    DELETE_COMPLETE,  # noqa: F821
    DELETE_FAILED,  # noqa: F821
    DELETE_IN_PROGRESS,  # noqa: F821
    DELETE_PENDING,  # noqa: F821
    LAUNCH_ERROR,  # noqa: F821
    LAUNCH_PENDING,  # noqa: F821
    LAUNCH_TIMEOUT,  # noqa: F821
    RESTORE_COMPLETE,  # noqa: F821
    RESTORE_FAILED,  # noqa: F821
    RESTORE_IN_PROGRESS,  # noqa: F821
    RESUME_COMPLETE,  # noqa: F821
    RESUME_FAILED,  # noqa: F821
    RESUME_IN_PROGRESS,  # noqa: F821
    ROLLBACK_COMPLETE,  # noqa: F821
    ROLLBACK_FAILED,  # noqa: F821
    ROLLBACK_IN_PROGRESS,  # noqa: F821
    SNAPSHOT_COMPLETE,  # noqa: F821
    SNAPSHOT_FAILED,  # noqa: F821
    SNAPSHOT_IN_PROGRESS,  # noqa: F821
    SUSPEND_COMPLETE,  # noqa: F821
    SUSPEND_FAILED,  # noqa: F821
    SUSPEND_IN_PROGRESS,  # noqa: F821
    SUSPEND_ISSUED,  # noqa: F821
    SUSPEND_PENDING,  # noqa: F821
    SUSPEND_RETRY,  # noqa: F821
    UPDATE_COMPLETE,  # noqa: F821
    UPDATE_FAILED,  # noqa: F821
    UPDATE_IN_PROGRESS  # noqa: F821
)

UP_STATES = (
    CREATE_COMPLETE,  # noqa: F821
    RESUME_COMPLETE,  # noqa: F821
    UPDATE_COMPLETE,  # noqa: F821
    ROLLBACK_COMPLETE,  # noqa: F821
    SNAPSHOT_COMPLETE  # noqa: F821
)

DOWN_STATES = (
    SUSPEND_COMPLETE,  # noqa: F821
    DELETE_COMPLETE  # noqa: F821
)

PENDING_STATES = (
    LAUNCH_PENDING,  # noqa: F821
    SUSPEND_PENDING,  # noqa: F821
    DELETE_PENDING  # noqa: F821
)

OCCUPANCY_STATES = (
    CREATE_COMPLETE,  # noqa: F821
    RESUME_COMPLETE,  # noqa: F821
    UPDATE_COMPLETE,  # noqa: F821
    ROLLBACK_COMPLETE,  # noqa: F821
    SNAPSHOT_COMPLETE,  # noqa: F821
    LAUNCH_PENDING,  # noqa: F821
    SUSPEND_PENDING,  # noqa: F821
    SUSPEND_ISSUED,  # noqa: F821
    SUSPEND_RETRY,  # noqa: F821
    SUSPEND_COMPLETE,  # noqa: F821
    DELETE_PENDING  # noqa: F821
)

SETTINGS_KEY = 'hastexo'

DEFAULT_SETTINGS = {
    "terminal_url": "/hastexo-xblock/",
    "terminal_color_scheme": "white-black",
    "terminal_font_name": "monospace",
    "terminal_font_size": "10",
    "instructions_layout": "above",
    "launch_timeout": 900,
    "remote_exec_timeout": 300,
    "suspend_timeout": 120,
    "suspend_interval": 60,
    "suspend_concurrency": 4,
    "suspend_task_timeout": 900,
    "check_timeout": 120,
    "delete_age": 14,
    "delete_attempts": 3,
    "delete_interval": 86400,
    "delete_task_timeout": 900,
    "sleep_timeout": 10,
    "ssh_connect_timeout": 10,
    "js_timeouts": {
        "status": 15000,
        "keepalive": 30000,
        "idle": 3600000,
        "check": 5000
    },
    "providers": {},
    "guacamole_js_version": '1.4.0',
    "lab_usage_limit": None,
    "lab_usage_limit_breach_policy": None
}


class RemoteExecException(Exception):
    pass


class RemoteExecTimeout(RemoteExecException):
    pass


if sys.version_info < (3,):
    def b(x):
        return x
else:
    import codecs

    def b(x):
        return codecs.latin_1_encode(x)[0]


def get_xblock_settings():
    try:
        xblock_settings = django_settings.XBLOCK_SETTINGS
    except AttributeError:
        settings = DEFAULT_SETTINGS
    else:
        settings = xblock_settings.get(
            SETTINGS_KEY, DEFAULT_SETTINGS)

    return settings


def update_stack(name, course_id, student_id, data):
    stack = Stack.objects.select_for_update().get(
        student_id=student_id,
        course_id=course_id,
        name=name
    )
    update_stack_fields(stack, data)
    stack.save(update_fields=list(data.keys()))


def update_stack_fields(stack, data):
    for field, value in data.items():
        if hasattr(stack, field):
            setattr(stack, field, value)


def get_stack(name, course_id, student_id, prop=None):
    stack = Stack.objects.get(
        student_id=student_id,
        course_id=course_id,
        name=name
    )

    if prop:
        return getattr(stack, prop)
    else:
        return stack


# If PyMongoError is raised here, try again (max attempts = 3)
# Before every subsequent retry, wait
# Use before_sleep_log to log attempts
# Reraise the exception from last attempt
@retry(retry=retry_if_exception_type(PyMongoError),
       stop=stop_after_attempt(3),
       wait=wait_exponential(),
       before_sleep=before_sleep_log(logger, logging.WARNING),
       reraise=True)
def read_from_contentstore(course_key, path):
    """
    Loads a file directly from the course's content store.

    """
    contents = None
    try:
        from xmodule.contentstore.content import StaticContent
        from xmodule.contentstore.django import contentstore
        from opaque_keys.edx.locator import CourseLocator
    except ImportError:
        # We're not running under edx-platform, so ignore.
        pass
    else:
        if isinstance(course_key, six.text_type):
            course_key = CourseLocator.from_string(course_key)
        loc = StaticContent.compute_location(course_key, path)
        asset = contentstore().find(loc)
        contents = asset.data

    return contents


def ssh_to(user, ip, key):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkey = paramiko.RSAKey.from_private_key(StringIO(key))

    settings = get_xblock_settings()
    sleep_timeout = settings.get("sleep_timeout", 10)
    ssh_connect_timeout = settings.get("ssh_connect_timeout", 10)

    connected = False
    while not connected:
        try:
            ssh.connect(ip,
                        username=user,
                        pkey=pkey,
                        timeout=ssh_connect_timeout)
        except (EOFError,
                AuthenticationException,
                SSHException,
                NoValidConnectionsError,
                SocketTimeout) as e:
            # Be more persistent than Paramiko normally
            # is, and keep retrying.
            logger.info("Got %s during SSH connection to ip (%s), retrying." %
                        (e.__class__.__name__, ip))
        except EnvironmentError as enve:
            if enve.errno in (errno.EAGAIN,
                              errno.ENETDOWN,
                              errno.ENETUNREACH,
                              errno.ENETRESET,
                              errno.ECONNABORTED,
                              errno.ECONNRESET,
                              errno.ENOTCONN,
                              errno.EHOSTDOWN):
                # Be more persistent than Paramiko normally
                # is, and keep retrying.
                logger.debug("Got errno %s during SSH connection "
                             "to ip (%s), retrying." % (enve.errno, ip))
            elif enve.errno in (errno.ECONNREFUSED,
                                errno.EHOSTUNREACH):
                # Paramiko should catch and wrap
                # these. They should never bubble
                # up. Still, continue being more
                # persistent, and retry.
                logger.warning("Got errno %s during SSH connection "
                               "to ip (%s). Paramiko bug? Retrying." %
                               (enve.errno, ip))
            else:
                # Anything else is an unexpected error.
                raise
        else:
            connected = True

        if not connected:
            time.sleep(sleep_timeout)

    return ssh


def remote_exec(ssh, script, params=None, reuse_sftp=None):
    if reuse_sftp:
        sftp = reuse_sftp
    else:
        sftp = ssh.open_sftp()

    # Generate a temporary filename
    script_file = '/tmp/.%s' % uuid.uuid4()

    # Open the file remotely and write the script out to it.
    f = sftp.open(script_file, 'w')
    f.write(script)
    f.close()

    # Make it executable.
    sftp.chmod(script_file, 0o775)

    # Add command line arguments, if any.
    if params:
        command = "%s %s" % (script_file, params)
    else:
        command = script_file

    # Run it.
    _, stdout, stderr = ssh.exec_command(command)

    # Wait for it to complete.
    settings = get_xblock_settings()
    timeout = settings.get("remote_exec_timeout", 300)
    try:
        start = time.time()
        while not stdout.channel.exit_status_ready():
            if timeout and time.time() >= start + timeout:
                error_msg = ("Remote execution timeout after [%d] seconds." %
                             timeout)
                raise RemoteExecTimeout(error_msg)

            time.sleep(1)
    finally:
        # Remove the file
        sftp.remove(script_file)

    # Check for errors
    retval = stdout.channel.recv_exit_status()
    error_msg = None
    if retval != 0:
        error_msg = stderr.read()
        raise RemoteExecException(error_msg)

    # Close the sftp session
    if not reuse_sftp:
        sftp.close()

    return retval
