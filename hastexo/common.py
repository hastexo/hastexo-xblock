import errno
import sys
import time
import uuid
import paramiko
import logging
import six

from io import StringIO
from paramiko.ssh_exception import (AuthenticationException,
                                    SSHException,
                                    NoValidConnectionsError)
from django.conf import settings as django_settings

from .models import Stack


logger = logging.getLogger(__name__)

CREATE_STATE = 'CREATE_COMPLETE'
RESUME_STATE = 'RESUME_COMPLETE'
UPDATE_STATE = 'UPDATE_COMPLETE'
ROLLBACK_STATE = 'ROLLBACK_COMPLETE'
SNAPSHOT_STATE = 'SNAPSHOT_COMPLETE'
LAUNCH_STATE = 'LAUNCH_PENDING'
LAUNCH_ERROR_STATE = 'LAUNCH_ERROR'
SUSPEND_STATE = 'SUSPEND_PENDING'
SUSPEND_FAILED_STATE = 'SUSPEND_FAILED'
SUSPEND_ISSUED_STATE = 'SUSPEND_ISSUED'
SUSPEND_RETRY_STATE = 'SUSPEND_RETRY'
SUSPENDED_STATE = 'SUSPEND_COMPLETE'
SUSPEND_IN_PROGRESS_STATE = 'SUSPEND_IN_PROGRESS'
RESUME_IN_PROGRESS_STATE = 'RESUME_IN_PROGRESS'
RESUME_FAILED_STATE = 'RESUME_FAILED'
DELETED_STATE = 'DELETE_COMPLETE'
DELETE_STATE = 'DELETE_PENDING'
DELETE_IN_PROGRESS_STATE = 'DELETE_IN_PROGRESS'
DELETE_FAILED_STATE = 'DELETE_FAILED'

UP_STATES = (
    CREATE_STATE,
    RESUME_STATE,
    UPDATE_STATE,
    ROLLBACK_STATE,
    SNAPSHOT_STATE
)

DOWN_STATES = (
    SUSPENDED_STATE,
    DELETED_STATE
)

PENDING_STATES = (
    LAUNCH_STATE,
    SUSPEND_STATE,
    DELETE_STATE
)

OCCUPANCY_STATES = (
    CREATE_STATE,
    RESUME_STATE,
    UPDATE_STATE,
    ROLLBACK_STATE,
    SNAPSHOT_STATE,
    LAUNCH_STATE,
    SUSPEND_STATE,
    SUSPEND_ISSUED_STATE,
    SUSPEND_RETRY_STATE,
    DELETE_STATE
)

SETTINGS_KEY = 'hastexo'

DEFAULT_SETTINGS = {
    "terminal_url": "/hastexo-xblock/",
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
    "js_timeouts": {
        "status": 15000,
        "keepalive": 30000,
        "idle": 3600000,
        "check": 5000
    },
    "providers": {}
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

    connected = False
    while not connected:
        try:
            ssh.connect(ip, username=user, pkey=pkey)
        except (EOFError,
                AuthenticationException,
                SSHException,
                NoValidConnectionsError) as e:
            # Be more persistent than Paramiko normally
            # is, and keep retrying.
            logger.debug("Got %s during SSH connection to ip (%s), retrying." %
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
    sleep_timeout = settings.get("sleep_timeout", 10)
    try:
        start = time.time()
        while not stdout.channel.exit_status_ready():
            if timeout and time.time() >= start + timeout:
                error_msg = ("Remote execution timeout after [%d] seconds." %
                             timeout)
                raise RemoteExecTimeout(error_msg)

            time.sleep(sleep_timeout)
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
