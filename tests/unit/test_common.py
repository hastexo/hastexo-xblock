import ddt
import errno

from django.test import TestCase
from mock import Mock, patch
from pymongo.errors import (
    PyMongoError,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
)
from hastexo.common import (
    read_from_contentstore,
    ssh_to,
    remote_exec,
    RemoteExecException,
    RemoteExecTimeout,
)

from socket import timeout as SocketTimeout

RETRY_SOCKET_ERRNOS = [
    errno.EAGAIN,
    errno.ENETDOWN,
    errno.ENETUNREACH,
    errno.ENETRESET,
    errno.ECONNABORTED,
    errno.ECONNRESET,
    errno.ENOTCONN,
    errno.ECONNREFUSED,
    errno.EHOSTDOWN,
    errno.EHOSTUNREACH
]


@ddt.ddt
class TestHastexoCommon(TestCase):
    def setUp(self):
        self.settings = {
            "sleep_timeout": 0,
            "remote_exec_timeout": 0.1,
        }

        patchers = {
            "uuid": patch("hastexo.common.uuid"),
            "paramiko": patch("hastexo.common.paramiko"),
            "settings": patch.dict("hastexo.common.DEFAULT_SETTINGS",
                                   self.settings),
        }

        self.mocks = {}
        for mock_name, patcher in patchers.items():
            self.mocks[mock_name] = patcher.start()
            self.addCleanup(patcher.stop)

    def test_read_from_contentstore(self):
        # Setup
        asset_mock = Mock()
        asset_mock.data = "bogus"
        contentstore_mock = Mock()
        contentstore_mock.return_value.find.return_value = asset_mock
        django_mock = Mock()
        django_mock.contentstore = contentstore_mock

        # Run
        with patch.dict('sys.modules', **{
            'xmodule': Mock(),
            'xmodule.contentstore': Mock(),
            'xmodule.contentstore.django': django_mock,
            'xmodule.contentstore.content': Mock(),
            'opaque_keys': Mock(),
            'opaque_keys.edx': Mock(),
            'opaque_keys.edx.locator': Mock(),
        }):
            content = read_from_contentstore("course_id", "path")

        # Assert
        self.assertEqual(content, "bogus")

    def test_read_from_contentstore_retry_succeed(self):
        # Setup
        asset_mock = Mock()
        asset_mock.data = "bogus"
        contentstore_mock = Mock()
        contentstore_mock.return_value.find.side_effect = [
            ConnectionFailure,
            NetworkTimeout,
            asset_mock
        ]
        django_mock = Mock()
        django_mock.contentstore = contentstore_mock

        # Run
        with patch.dict('sys.modules', **{
            'xmodule': Mock(),
            'xmodule.contentstore': Mock(),
            'xmodule.contentstore.django': django_mock,
            'xmodule.contentstore.content': Mock(),
            'opaque_keys': Mock(),
            'opaque_keys.edx': Mock(),
            'opaque_keys.edx.locator': Mock(),
        }):
            content = read_from_contentstore("course_id", "path")

        # Assert
        self.assertEqual(content, "bogus")
        self.assertEqual(contentstore_mock.return_value.find.call_count, 3)

    def test_read_from_contentstore_retry_fail(self):
        # Setup
        contentstore_mock = Mock()
        contentstore_mock.return_value.find.side_effect = [
            ConnectionFailure,
            NetworkTimeout,
            ServerSelectionTimeoutError,
        ]
        django_mock = Mock()
        django_mock.contentstore = contentstore_mock

        # Run
        with patch.dict('sys.modules', **{
            'xmodule': Mock(),
            'xmodule.contentstore': Mock(),
            'xmodule.contentstore.django': django_mock,
            'xmodule.contentstore.content': Mock(),
            'opaque_keys': Mock(),
            'opaque_keys.edx': Mock(),
            'opaque_keys.edx.locator': Mock(),
        }):
            with self.assertRaises(PyMongoError):
                read_from_contentstore("course_id", "path")

    def test_read_from_contentstore_no_xmodule(self):
        content = read_from_contentstore("course_id", "path")
        self.assertIsNone(content)

    def test_ssh_to(self):
        # Setup
        ssh_mock = Mock()
        self.mocks["paramiko"].SSHClient.return_value = ssh_mock
        self.mocks["paramiko"].RSAKey.from_private_key.return_value = "pkey"

        # Run
        ssh = ssh_to("user", "ip", u"key")

        # Assert
        self.assertEqual(ssh, ssh_mock)
        ssh_mock.connect.assert_called_with("ip",
                                            username="user",
                                            pkey="pkey",
                                            timeout=10)

    def test_ssh_to_retries(self):
        # Setup
        ssh_mock = Mock()
        self.mocks["paramiko"].SSHClient.return_value = ssh_mock
        self.mocks["paramiko"].RSAKey.from_private_key.return_value = "pkey"
        ssh_mock.connect.side_effect = [
            SocketTimeout,
            EOFError(""),
            True,
        ]

        # Run
        ssh = ssh_to("user", "ip", u"key")

        # Assert
        self.assertEqual(ssh, ssh_mock)
        self.assertEqual(3, len(ssh_mock.connect.mock_calls))

    @ddt.data(*RETRY_SOCKET_ERRNOS)
    def test_ssh_to_retries_on_certain_socket_errnos(self, errno):
        # Setup
        ssh_mock = Mock()
        self.mocks["paramiko"].SSHClient.return_value = ssh_mock
        self.mocks["paramiko"].RSAKey.from_private_key.return_value = "pkey"
        ssh_mock.connect.side_effect = [
            EnvironmentError(errno, ""),
            True,
        ]

        # Run
        ssh = ssh_to("user", "ip", u"key")

        # Assert
        self.assertEqual(ssh, ssh_mock)
        self.assertEqual(2, len(ssh_mock.connect.mock_calls))

    def test_ssh_to_dont_retry_on_other_socket_errnos(self):
        # Setup
        ssh_mock = Mock()
        self.mocks["paramiko"].SSHClient.return_value = ssh_mock
        self.mocks["paramiko"].RSAKey.from_private_key.return_value = "pkey"
        ssh_mock.connect.side_effect = EnvironmentError(errno.ENOTSOCK, "")

        # Run
        with self.assertRaises(EnvironmentError):
            ssh_to("user", "ip", u"key")

    def test_ssh_to_explodes(self):
        # Setup
        ssh_mock = Mock()
        self.mocks["paramiko"].SSHClient.return_value = ssh_mock
        self.mocks["paramiko"].RSAKey.from_private_key.return_value = "pkey"
        ssh_mock.connect.side_effect = Exception("")

        # Run
        with self.assertRaises(Exception):
            ssh_to("user", "ip", u"key")

    def test_remote_exec(self):
        # Setup
        ssh_mock = Mock()
        sftp_mock = Mock()
        ssh_mock.open_sftp.return_value = sftp_mock
        stdout_mock = Mock()
        stdout_mock.channel.exit_status_ready.return_value = True
        stdout_mock.channel.recv_exit_status.return_value = 0
        ssh_mock.exec_command.return_value = (None, stdout_mock, None)

        # Run
        retval = remote_exec(ssh_mock, "script")

        # Assert
        self.assertEqual(0, retval)
        sftp_mock.open.assert_called()
        sftp_mock.remove.assert_called()
        sftp_mock.close.assert_called()

    def test_remote_exec_with_params(self):
        # Setup
        ssh_mock = Mock()
        sftp_mock = Mock()
        ssh_mock.open_sftp.return_value = sftp_mock
        stdout_mock = Mock()
        stdout_mock.channel.exit_status_ready.return_value = True
        stdout_mock.channel.recv_exit_status.return_value = 0
        ssh_mock.exec_command.return_value = (None, stdout_mock, None)
        self.mocks["uuid"].uuid4.return_value = "a_very_predictable_uuid"

        # Run
        retval = remote_exec(ssh_mock, "script", params="resume")

        # Assert
        self.assertEqual(0, retval)
        expected_command = "/tmp/.a_very_predictable_uuid resume"
        ssh_mock.exec_command.assert_called_with(expected_command)
        sftp_mock.open.assert_called()
        sftp_mock.remove.assert_called()
        sftp_mock.close.assert_called()

    def test_remote_exec_timeout(self):
        # Setup
        ssh_mock = Mock()
        sftp_mock = Mock()
        ssh_mock.open_sftp.return_value = sftp_mock
        stdout_mock = Mock()
        stdout_mock.channel.exit_status_ready.return_value = False
        ssh_mock.exec_command.return_value = (None, stdout_mock, None)

        # Run
        with self.assertRaises(RemoteExecTimeout):
            remote_exec(ssh_mock, "script")

        sftp_mock.remove.assert_called()

    def test_remote_exec_reuse_sftp(self):
        # Setup
        ssh_mock = Mock()
        sftp_mock = Mock()
        stdout_mock = Mock()
        stdout_mock.channel.exit_status_ready.return_value = True
        stdout_mock.channel.recv_exit_status.return_value = 0
        ssh_mock.exec_command.side_effect = [
            (None, stdout_mock, None)
        ]

        # Run
        retval = remote_exec(ssh_mock, "script", reuse_sftp=sftp_mock)

        # Assert
        self.assertEqual(0, retval)
        sftp_mock.open.assert_called()
        sftp_mock.remove.assert_called()
        sftp_mock.close.assert_not_called()

    def test_remote_exec_error(self):
        # Setup
        ssh_mock = Mock()
        sftp_mock = Mock()
        ssh_mock.open_sftp.return_value = sftp_mock
        stdout_mock = Mock()
        stdout_mock.channel.exit_status_ready.return_value = True
        stdout_mock.channel.recv_exit_status.return_value = 1
        stderr_mock = Mock()
        stderr_mock.read.return_value = "error message"
        ssh_mock.exec_command.return_value = (None, stdout_mock, stderr_mock)

        # Run
        with self.assertRaises(RemoteExecException):
            remote_exec(ssh_mock, "script")

        sftp_mock.remove.assert_called()
