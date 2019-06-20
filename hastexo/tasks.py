import time
import os
import uuid
import paramiko
import traceback
import socket

from django.db import transaction
from celery import Task
from celery.utils.log import get_task_logger
from celery.exceptions import SoftTimeLimitExceeded
from io import StringIO
from paramiko.ssh_exception import (AuthenticationException,
                                    SSHException,
                                    NoValidConnectionsError)

from .models import Stack
from .provider import Provider, ProviderException
from .common import (OCCUPANCY_STATES, get_xblock_settings, update_stack)

logger = get_task_logger(__name__)

CLEANUP_SUSPEND = 1
CLEANUP_DELETE = 2

PING_COMMAND = "ping -c 1 -W %d %s >/dev/null 2>&1"


class LaunchStackFailed(Exception):
    provider = None
    status = ""
    error_msg = ""
    suspend = False
    delete = False

    def __init__(self, provider, status, error_msg, cleanup=0):
        super(LaunchStackFailed, self).__init__()

        self.provider = provider
        self.status = status
        self.error_msg = error_msg

        if cleanup == CLEANUP_SUSPEND:
            self.suspend = True
        elif cleanup == CLEANUP_DELETE:
            self.delete = True


class LaunchStackTask(Task):
    """
    Launch, or if it already exists and is suspended, resume a stack for the
    user.

    """

    def run(self, **kwargs):
        """
        Run the celery task.

        """
        # Initialize providers
        self.providers = []
        for provider in kwargs.get("providers", []):
            p = Provider.init(provider["name"])
            p.set_capacity(provider["capacity"])
            p.set_template(provider["template"])

            environment = provider.get("environment")
            if environment:
                p.set_environment(environment)

            self.providers.append(p)

        # Set the rest of the arguments.
        for key, value in kwargs.items():
            if key == "providers":
                continue
            setattr(self, key, value)

        self.settings = get_xblock_settings()
        task_timeouts = self.settings.get('task_timeouts', {})
        self.sleep_seconds = task_timeouts.get('sleep', 5)

        try:
            # Launch the stack and wait for it to complete.
            stack_data = self.launch_stack()
        except LaunchStackFailed as e:
            logger.error(e.error_msg)

            # In case of failure, only return the provider if this was a failed
            # resume attempt.
            provider_name = ""
            if e.suspend:
                provider_name = e.provider.name

            stack_data = {
                'status': e.status,
                'error_msg': e.error_msg,
                'ip': None,
                'user': "",
                'key': "",
                'password': "",
                'provider': provider_name
            }

            # Roll back in case of failure
            self.cleanup_stack(e)

        return stack_data

    def update_stack(self, data):
        return update_stack(self.stack_name,
                            self.course_id,
                            self.student_id,
                            data)

    def sleep(self):
        time.sleep(self.sleep_seconds)

    def get_provider(self, name):
        try:
            provider = next(p for p in self.providers if p.name == name)
        except StopIteration:
            provider = None

        return provider

    def launch_stack(self):
        """
        Launch the user stack, either by creating or resuming it.  If a reset
        is requested, delete the stack and recreate it.

        """
        logger.info("Launching stack [%s]." % self.stack_name)

        # Fetch stack information from the database, but do so atomically to
        # make sure the original request had a chance to commit.
        with transaction.atomic():
            stack = Stack.objects.select_for_update().get(
                student_id=self.student_id,
                course_id=self.course_id,
                name=self.stack_name
            )

        if stack.provider:
            provider = self.get_provider(stack.provider)
            if self.reset:
                self.try_provider(provider, True)

                stack_data = self.try_all_providers()
            else:
                stack_data = self.try_provider(provider)
        else:
            stack_data = self.try_all_providers()

        return stack_data

    def get_provider_stack_count(self, provider):
        stack_count = Stack.objects.filter(
            course_id__exact=self.course_id,
            provider__exact=provider.name,
            status__in=list(OCCUPANCY_STATES)
        ).exclude(
            name__exact=self.stack_name
        ).count()

        return stack_count

    def try_all_providers(self):
        stack_data = None

        # Try launching the stack in all providers, in sequence
        for index, provider in enumerate(self.providers):
            # Check if provider is full.  If it is, try the next one.
            if provider.capacity == 0:
                logger.info("Stack [%s]: provider [%s] is disabled." %
                            (self.stack_name, provider.name))
                continue
            elif provider.capacity > 0:
                stack_count = self.get_provider_stack_count(provider)
                if stack_count >= provider.capacity:
                    logger.info("Stack [%s]: provider [%s] is full, "
                                "with capacity [%d/%d]." %
                                (self.stack_name, provider.name,
                                 stack_count, provider.capacity))
                    continue

            # Launch stack in provider.  If successful, don't continue trying.
            try:
                self.update_stack({"provider": provider.name})
                stack_data = self.try_provider(provider)
                break
            except LaunchStackFailed as e:
                self.update_stack({"provider": ""})
                # If this is the last provider, or it was a timeout, re-raise
                # the exception and let the parent clean up.
                if (index == (len(self.providers) - 1) or
                   e.status == "LAUNCH_TIMEOUT"):
                    raise
                else:
                    logger.error(e.error_msg)

                    # Clean up before continuing on to the next provider.
                    try:
                        self.cleanup_stack(e)
                    except SoftTimeLimitExceeded:
                        error_msg = "Timeout cleaning up stack [%s]." % (
                            self.stack_name)
                        raise LaunchStackFailed(e.provider, "LAUNCH_TIMEOUT",
                                                error_msg)

        if stack_data is None:
            logger.error("No providers available for stack [%s]." %
                         (self.stack_name))
            error_msg = ("There are no providers available to launch your "
                         "environment in.")
            raise LaunchStackFailed("", "CREATE_FAILED", error_msg)

        return stack_data

    def try_provider(self, provider, reset=False):
        """
        Launch stack on a provider.  If a reset is requested, don't create the
        stack: just delete it.

        """
        error_msg = ""
        was_resumed = False
        stack_data = {}

        if not reset:
            logger.info("Trying to launch stack [%s] on provider [%s]." %
                        (self.stack_name, provider.name))
        else:
            logger.info("Resetting stack [%s] on provider [%s]." %
                        (self.stack_name, provider.name))

        # Check if the stack actually exists
        try:
            provider_stack = provider.get_stack(self.stack_name)
        except ProviderException as e:
            error_msg = ("Error retrieving [%s] stack information: %s" %
                         (self.stack_name, e))
            raise LaunchStackFailed(provider, "CREATE_FAILED", error_msg)
        except SoftTimeLimitExceeded:
            error_msg = "Timeout fetching stack [%s] information." % (
                self.stack_name)
            raise LaunchStackFailed(provider, "LAUNCH_TIMEOUT", error_msg)

        # If stack is undergoing a change of state, wait until it
        # finishes.
        try:
            while 'IN_PROGRESS' in provider_stack["status"]:
                try:
                    # Sleep to avoid throttling.
                    self.sleep()

                    provider_stack = provider.get_stack(self.stack_name)
                except ProviderException as e:
                    error_msg = ("Error waiting for stack [%s] to change "
                                 "state: %s" % (self.stack_name, e))
                    raise LaunchStackFailed(provider, "CREATE_FAILED",
                                            error_msg)
        except SoftTimeLimitExceeded:
            error_msg = "Timeout waiting for stack [%s] state change." % (
                self.stack_name)
            raise LaunchStackFailed(provider, "LAUNCH_TIMEOUT", error_msg)

        # Reset the stack, if necessary
        if reset:
            try:
                if provider_stack["status"] != 'DELETE_COMPLETE':
                    # Sleep to avoid throttling.
                    self.sleep()

                    logger.info("Resetting stack [%s]." % self.stack_name)
                    provider_stack = provider.delete_stack(self.stack_name)
            except ProviderException as e:
                error_msg = ("Error deleting stack [%s]: %s" %
                             (self.stack_name, e))
                raise LaunchStackFailed(provider, "CREATE_FAILED", error_msg)
            except SoftTimeLimitExceeded:
                error_msg = "Timeout resetting stack [%s]." % self.stack_name
                raise LaunchStackFailed(provider, "LAUNCH_TIMEOUT", error_msg)
        else:
            # Create the stack if it doesn't exist
            try:
                if provider_stack["status"] == 'DELETE_COMPLETE':
                    # Sleep to avoid throttling.
                    self.sleep()

                    logger.info("Creating stack [%s]." % self.stack_name)
                    provider_stack = provider.create_stack(self.stack_name,
                                                           self.stack_run)
            except ProviderException as e:
                error_msg = ("Error creating stack [%s]: %s" %
                             (self.stack_name, e))
                raise LaunchStackFailed(provider, "CREATE_FAILED", error_msg,
                                        CLEANUP_DELETE)
            except SoftTimeLimitExceeded:
                error_msg = "Timeout creating stack [%s]." % self.stack_name
                raise LaunchStackFailed(provider, "LAUNCH_TIMEOUT", error_msg,
                                        CLEANUP_DELETE)
            # If stack is suspended, resume it.
            try:
                if provider_stack["status"] == 'SUSPEND_COMPLETE' or \
                        provider_stack["status"] == 'RESUME_COMPLETE':
                    # Store the fact the stack was resumed
                    was_resumed = True

                if provider_stack["status"] == 'SUSPEND_COMPLETE':
                    # Sleep to avoid throttling.
                    self.sleep()

                    logger.info("Resuming stack [%s]." % self.stack_name)
                    provider_stack = provider.resume_stack(self.stack_name)
            except ProviderException as e:
                error_msg = ("Error resuming stack [%s]: %s" %
                             (self.stack_name, e))
                raise LaunchStackFailed(provider, "RESUME_FAILED", error_msg,
                                        CLEANUP_SUSPEND)
            except SoftTimeLimitExceeded:
                error_msg = "Timeout resuming stack [%s]." % self.stack_name
                raise LaunchStackFailed(provider, "LAUNCH_TIMEOUT", error_msg,
                                        CLEANUP_SUSPEND)

            # Launch completed successfully.  Wait for provisioning, collect
            # its IP address, and save the private key.
            try:
                check_data = self.check_stack(provider_stack["outputs"],
                                              was_resumed, provider)
            except SoftTimeLimitExceeded:
                if was_resumed:
                    cleanup = CLEANUP_SUSPEND
                else:
                    cleanup = CLEANUP_DELETE

                error_msg = "Timeout verifying stack [%s]." % self.stack_name
                raise LaunchStackFailed(provider, "LAUNCH_TIMEOUT", error_msg,
                                        cleanup)

            stack_data = {
                "status": provider_stack["status"],
                "error_msg": error_msg,
                "ip": check_data["ip"],
                "user": self.stack_user_name,
                "key": check_data["key"],
                "password": check_data["password"],
                "provider": provider.name
            }

        return stack_data

    def cleanup_stack(self, e):
        """
        Clean up stack after a LaunchStackFailed exception.

        """
        if e.delete or e.suspend:
            if e.delete:
                logger.error("Deleting unsuccessfully "
                             "created stack [%s]." % self.stack_name)
                try:
                    e.provider.delete_stack(self.stack_name, False)
                except ProviderException as e:
                    logger.error("Failure deleting stack "
                                 "[%s], with error [%s]." % (
                                     self.stack_name, e))
            elif e.suspend:
                logger.error("Suspending unsuccessfully "
                             "resumed stack [%s]." % self.stack_name)
                try:
                    e.provider.suspend_stack(self.stack_name)
                except ProviderException as e:
                    logger.error("Failure suspending stack "
                                 "[%s], with error [%s]." % (
                                     self.stack_name, e))

    def wait_for_ping(self, stack_ip):
        ping_command = PING_COMMAND % (self.sleep_seconds, stack_ip)
        while os.system(ping_command) != 0:
            self.sleep()

    def setup_ssh(self, stack_key):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = paramiko.RSAKey.from_private_key(StringIO(stack_key))

        return (ssh, pkey)

    def wait_for_ssh(self, stack_key, stack_ip, was_resumed, provider):
        ssh, pkey = self.setup_ssh(stack_key)
        connected = False
        while not connected:
            try:
                ssh.connect(stack_ip, username=self.stack_user_name, pkey=pkey)
            except (EOFError,
                    AuthenticationException,
                    SSHException,
                    NoValidConnectionsError):
                self.sleep()
            except SoftTimeLimitExceeded:
                raise
            except Exception:
                if was_resumed:
                    error_status = 'RESUME_FAILED'
                    cleanup = CLEANUP_SUSPEND
                else:
                    error_status = 'CREATE_FAILED'
                    cleanup = CLEANUP_DELETE

                logger.error("Exception when checking SSH connection to stack "
                             "[%s]: %s" % (self.stack_name,
                                           traceback.format_exc()))
                error_msg = ("Could not connect to your lab environment "
                             "[%s]." % self.stack_name)
                raise LaunchStackFailed(provider, error_status, error_msg,
                                        cleanup)
            else:
                ssh.close()
                connected = True

    def wait_for_rdp(self, stack_ip):
        port = getattr(self, 'port', None)
        if not port:
            port = 3389

        connected = False
        s = socket.socket()
        s.settimeout(self.sleep_seconds)
        while not connected:
            try:
                s.connect((stack_ip, port))
            except SoftTimeLimitExceeded:
                raise
            except Exception:
                self.sleep()
            else:
                connected = True
            finally:
                s.close()

    def check_stack(self, stack_outputs, was_resumed, provider):
        """
        Fetch stack outputs, check that the stack has a public IP address, a
        private key, and is network accessible after rebooting any servers.
        Save its private key, and check that it is possible to SSH into the
        stack using it.

        """
        stack_ip = None
        stack_key = ""
        stack_password = ""

        logger.debug("Verifying stack [%s] " % self.stack_name)

        # Get stack outputs
        stack_ip = stack_outputs.get("public_ip")
        stack_key = stack_outputs.get("private_key")
        stack_password = stack_outputs.get("password")

        if stack_ip is None or not stack_key:
            if was_resumed:
                error_status = 'RESUME_FAILED'
                cleanup = CLEANUP_SUSPEND
            else:
                error_status = 'CREATE_FAILED'
                cleanup = CLEANUP_DELETE

            error_msg = ("Stack [%s] did not provide "
                         "IP or private key." % self.stack_name)
            raise LaunchStackFailed(provider, error_status, error_msg, cleanup)

        # Wait until stack is network accessible
        logger.info("Waiting for stack [%s] "
                    "to become network accessible "
                    "at [%s]" % (self.stack_name, stack_ip))
        self.wait_for_ping(stack_ip)

        # Now wait until environment is fully provisioned.  One of the
        # requirements for the Heat template is for it to disallow SSH
        # access to the training user while provisioning is going on.
        logger.info("Checking SSH connection "
                    "for stack [%s] at [%s]" % (self.stack_name, stack_ip))
        self.wait_for_ssh(stack_key, stack_ip, was_resumed, provider)

        # If the protocol is RDP, wait for xrdp to come up.
        protocol = getattr(self, 'protocol', None)
        if protocol and protocol == "rdp":
            logger.info("Checking RDP connection "
                        "for stack [%s] at [%s]" % (self.stack_name, stack_ip))
            self.wait_for_rdp(stack_ip)

        check_data = {
            "ip": stack_ip,
            "key": stack_key,
            "password": stack_password
        }

        return check_data


class CheckStudentProgressTask(Task):
    """
    Check student progress by running a set of scripts via SSH.

    """

    def run(self, **kwargs):
        """
        Run the celery task.

        """
        for key, value in kwargs.items():
            setattr(self, key, value)

        try:
            # Open SSH connection to the public facing node
            ssh = self.open_ssh_connection()

            # Run tests on the stack
            res = self.run_tests(ssh)
        except SoftTimeLimitExceeded:
            res = {
                'status': 'CHECK_PROGRESS_TIMEOUT',
                'error': True
            }
        finally:
            # Close the connection
            ssh.close()

        return res

    def run_tests(self, ssh):
        sftp = ssh.open_sftp()

        # Write scripts out, run them, and keep score.
        score = 0
        errors = []
        for test in self.tests:
            # Generate a temporary filename
            script = '/tmp/.%s' % uuid.uuid4()

            # Open the file remotely and write the script out to it.
            f = sftp.open(script, 'w')
            f.write(test)
            f.close()

            # Make it executable and run it.
            sftp.chmod(script, 0o775)
            _, stdout, stderr = ssh.exec_command(script)
            retval = stdout.channel.recv_exit_status()
            if retval == 0:
                score += 1
            else:
                error = stderr.read()
                if error:
                    errors.append(error)

            # Remove the script
            sftp.remove(script)

        return {
            'status': 'CHECK_PROGRESS_COMPLETE',
            'pass': score,
            'total': len(self.tests),
            'errors': errors
        }

    def open_ssh_connection(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = paramiko.RSAKey.from_private_key(StringIO(self.stack_key))
        ssh.connect(self.stack_ip, username=self.stack_user_name, pkey=pkey)

        return ssh
