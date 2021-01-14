import time
import os
import traceback
import socket
import logging
import ipaddress

from django.db import connection, transaction
from django.db.utils import OperationalError
from django.utils import timezone
from celery import Task
from celery.utils.log import get_task_logger
from celery.exceptions import SoftTimeLimitExceeded
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from .models import Stack
from .provider import Provider, ProviderException
from .common import (
    DELETE,
    IN_PROGRESS,
    UP_STATES,
    OCCUPANCY_STATES,
    RESUME_COMPLETE,
    RESUME_FAILED,
    SUSPEND_COMPLETE,
    SUSPEND_FAILED,
    CREATE_FAILED,
    DELETE_COMPLETE,
    DELETE_IN_PROGRESS,
    DELETE_FAILED,
    LAUNCH_TIMEOUT,
    get_xblock_settings,
    update_stack_fields,
    ssh_to,
    read_from_contentstore,
    remote_exec,
    RemoteExecException,
    RemoteExecTimeout,
)

logger = get_task_logger(__name__)

CLEANUP_SUSPEND = 1
CLEANUP_DELETE = 2

PING_COMMAND = "%s -c 1 -W %d %s >/dev/null 2>&1"


def close_connection_on_retry(retry_state):
    """Simple wrapper that accepts retry_state as a parameter,
    so that it can be used as a retry callback."""
    connection.close()


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


class HastexoTask(Task):
    """
    Abstract task.

    """
    sleep_timeout = None

    def get_sleep_timeout(self):
        if self.sleep_timeout is None:
            settings = get_xblock_settings()
            self.sleep_timeout = settings.get("sleep_timeout", 10)

        return self.sleep_timeout

    def sleep(self, multiplier=1):
        sleep_time = multiplier * self.get_sleep_timeout()
        logger.debug("Sleeping for %i seconds" % sleep_time)
        time.sleep(sleep_time)

    # If OperationalError is raised here, try again (max attempts = 3)
    # Before every subsequent retry, wait
    # Use before_sleep to close connection
    # Use after_log to log attempts
    # Reraise the exception from last attempt
    #
    # Reference:
    # https://tenacity.readthedocs.io/en/latest/
    @retry(retry=retry_if_exception_type(OperationalError),
           stop=stop_after_attempt(3),
           wait=wait_exponential(),
           after=close_connection_on_retry,
           before_sleep=before_sleep_log(logger, logging.WARNING),
           reraise=True)
    @transaction.atomic
    def update_stack(self, data):
        stack = Stack.objects.select_for_update().get(id=self.stack_id)
        update_stack_fields(stack, data)
        stack.save(update_fields=list(data.keys()))


class LaunchStackTask(HastexoTask):
    """
    Launch, or if it already exists and is suspended, resume a stack for the
    user.

    """

    def run(self, **kwargs):
        """
        Run the celery task.

        """
        # Set the arguments.
        for key, value in kwargs.items():
            setattr(self, key, value)

        # Get the stack
        stack = Stack.objects.get(id=self.stack_id)

        # Initialize parameters
        self.protocol = stack.protocol
        self.port = stack.port
        self.stack_run = stack.run
        self.stack_name = stack.name
        self.stack_user_name = stack.user
        self.course_id = stack.course_id
        self.student_id = stack.student_id
        self.hook_events = stack.hook_events

        # Initialize hook script
        self.hook_script = None
        if stack.hook_script:
            self.hook_script = read_from_contentstore(
                stack.course_id,
                stack.hook_script
            )

        # Initialize providers
        self.providers = []
        for provider in stack.providers:
            p = Provider.init(provider["name"])
            p.set_capacity(provider["capacity"])

            template = read_from_contentstore(
                stack.course_id,
                provider["template"]
            )
            p.set_template(template)

            environment_path = provider.get("environment")
            if environment_path:
                environment = read_from_contentstore(
                    stack.course_id,
                    environment_path
                )
                p.set_environment(environment)

            self.providers.append(p)

        try:
            # Launch the stack and wait for it to complete.
            stack_data = self.launch_stack(stack.provider)
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

        # Don't wait for the user to check results.  Update the database
        # immediately.
        self.update_stack(stack_data)

    def get_provider(self, name):
        try:
            provider = next(p for p in self.providers if p.name == name)
        except StopIteration:
            provider = None

        return provider

    def launch_stack(self, provider_name=None):
        """
        Launch the user stack, either by creating or resuming it.  If a reset
        is requested, delete the stack and recreate it.

        """
        logger.info("Launching stack [%s]." % self.stack_name)

        if provider_name:
            provider = self.get_provider(provider_name)
            if self.reset:
                self.try_provider(provider, True)

                stack_data = self.try_all_providers()
            else:
                stack_data = self.try_provider(provider)
        else:
            stack_data = self.try_all_providers()

        return stack_data

    # If OperationalError is raised here, try again (max attempts = 3)
    # Before every subsequent retry, wait
    # Use before_sleep to close connection
    # Use after_log to log attempts
    # Reraise the exception from last attempt
    @retry(retry=retry_if_exception_type(OperationalError),
           stop=stop_after_attempt(3),
           wait=wait_exponential(),
           after=close_connection_on_retry,
           before_sleep=before_sleep_log(logger, logging.WARNING),
           reraise=True)
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
                   e.status == LAUNCH_TIMEOUT):
                    raise
                else:
                    logger.error(e.error_msg)

                    # Clean up before continuing on to the next provider.
                    try:
                        self.cleanup_stack(e)
                    except SoftTimeLimitExceeded:
                        error_msg = "Timeout cleaning up stack [%s]." % (
                            self.stack_name)
                        raise LaunchStackFailed(e.provider, LAUNCH_TIMEOUT,
                                                error_msg)

        if stack_data is None:
            logger.error("No providers available for stack [%s]." %
                         (self.stack_name))
            error_msg = ("There are no providers available to launch your "
                         "environment in.")
            raise LaunchStackFailed("", CREATE_FAILED, error_msg)

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
            raise LaunchStackFailed(provider, CREATE_FAILED, error_msg)
        except SoftTimeLimitExceeded:
            error_msg = "Timeout fetching stack [%s] information." % (
                self.stack_name)
            raise LaunchStackFailed(provider, LAUNCH_TIMEOUT, error_msg)

        # If stack is undergoing a change of state, wait until it
        # finishes.
        try:
            while IN_PROGRESS in provider_stack["status"]:
                try:
                    # Sleep to avoid throttling.
                    self.sleep()

                    provider_stack = provider.get_stack(self.stack_name)
                except ProviderException as e:
                    error_msg = ("Error waiting for stack [%s] to change "
                                 "state: %s" % (self.stack_name, e))
                    if DELETE in provider_stack["status"]:
                        raise LaunchStackFailed(provider, CREATE_FAILED,
                                                error_msg)
                    else:
                        raise LaunchStackFailed(provider, RESUME_FAILED,
                                                error_msg, CLEANUP_SUSPEND)
        except SoftTimeLimitExceeded:
            error_msg = "Timeout waiting for stack [%s] state change." % (
                self.stack_name)
            raise LaunchStackFailed(provider, LAUNCH_TIMEOUT, error_msg)

        # Reset the stack, if necessary
        if reset:
            try:
                if provider_stack["status"] != DELETE_COMPLETE:
                    # Sleep to avoid throttling.
                    self.sleep()

                    logger.info("Resetting stack [%s]." % self.stack_name)
                    provider_stack = provider.delete_stack(self.stack_name)
            except ProviderException as e:
                error_msg = ("Error deleting stack [%s]: %s" %
                             (self.stack_name, e))
                raise LaunchStackFailed(provider, CREATE_FAILED, error_msg)
            except SoftTimeLimitExceeded:
                error_msg = "Timeout resetting stack [%s]." % self.stack_name
                raise LaunchStackFailed(provider, LAUNCH_TIMEOUT, error_msg)
        else:
            # Create the stack if it doesn't exist
            try:
                if provider_stack["status"] == DELETE_COMPLETE:
                    # Sleep to avoid throttling.
                    self.sleep()

                    logger.info("Creating stack [%s]." % self.stack_name)
                    provider_stack = provider.create_stack(self.stack_name,
                                                           self.stack_run)
            except ProviderException as e:
                error_msg = ("Error creating stack [%s]: %s" %
                             (self.stack_name, e))
                raise LaunchStackFailed(provider, CREATE_FAILED, error_msg,
                                        CLEANUP_DELETE)
            except SoftTimeLimitExceeded:
                error_msg = "Timeout creating stack [%s]." % self.stack_name
                raise LaunchStackFailed(provider, LAUNCH_TIMEOUT, error_msg,
                                        CLEANUP_DELETE)
            # If stack is suspended, resume it.
            try:
                if provider_stack["status"] == SUSPEND_COMPLETE or \
                        provider_stack["status"] == RESUME_COMPLETE:
                    # Store the fact the stack was resumed
                    was_resumed = True

                if provider_stack["status"] == SUSPEND_COMPLETE:
                    # Sleep to avoid throttling.
                    self.sleep()

                    logger.info("Resuming stack [%s]." % self.stack_name)
                    provider_stack = provider.resume_stack(self.stack_name)
            except ProviderException as e:
                error_msg = ("Error resuming stack [%s]: %s" %
                             (self.stack_name, e))
                raise LaunchStackFailed(provider, RESUME_FAILED, error_msg,
                                        CLEANUP_SUSPEND)
            except SoftTimeLimitExceeded:
                error_msg = "Timeout resuming stack [%s]." % self.stack_name
                raise LaunchStackFailed(provider, LAUNCH_TIMEOUT, error_msg,
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
                raise LaunchStackFailed(provider, LAUNCH_TIMEOUT, error_msg,
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
        # The "ping" utility on Ubuntu Xenial does not work with
        # IPv6. We thus have to parse the IP address, and use ping6 if
        # it's an IPv6 one.
        ping_command = PING_COMMAND % (
            'ping6' if ipaddress.ip_address(stack_ip).version == 6 else 'ping',
            self.get_sleep_timeout(),
            stack_ip
        )
        logger.debug(
            'Testing connectivity to stack [%s] with "%s"' % (self.stack_name,
                                                              ping_command)
        )
        while os.system(ping_command) != 0:
            self.sleep()

    def wait_for_ssh(self, stack_key, stack_ip, was_resumed, provider):
        try:
            ssh = ssh_to(self.stack_user_name, stack_ip, stack_key)
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            if was_resumed:
                error_status = RESUME_FAILED
                cleanup = CLEANUP_SUSPEND
            else:
                error_status = CREATE_FAILED
                cleanup = CLEANUP_DELETE

            logger.error("Exception when checking SSH connection to stack "
                         "[%s]: %s" % (self.stack_name,
                                       traceback.format_exc()))
            error_msg = ("Could not connect to your lab environment "
                         "[%s]." % self.stack_name)
            raise LaunchStackFailed(provider, error_status, error_msg,
                                    cleanup)

        return ssh

    def wait_for_rdp(self, stack_ip):
        port = getattr(self, 'port', None)
        if not port:
            port = 3389

        connected = False
        s = socket.socket()
        s.settimeout(self.get_sleep_timeout())
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
                error_status = RESUME_FAILED
                cleanup = CLEANUP_SUSPEND
            else:
                error_status = CREATE_FAILED
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
        ssh = self.wait_for_ssh(stack_key, stack_ip, was_resumed, provider)

        try:
            # If we're resuming and there's a resume hook, execute it.
            if (was_resumed and
                    self.hook_script and
                    self.hook_events and
                    isinstance(self.hook_events, dict) and
                    self.hook_events.get("resume", False)):
                logger.info("Executing post-resume hook for stack [%s] "
                            "at [%s]" % (self.stack_name, stack_ip))
                try:
                    remote_exec(ssh, self.hook_script, params="resume")
                except Exception as e:
                    # We don't fail, as the user may have inadvertently broken
                    # the stack.
                    logger.error("Error running resume hook script on stack "
                                 "[%s]: %s" % (self.stack_name, str(e)))
        finally:
            ssh.close()

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


class SuspendStackTask(HastexoTask):
    """
    Suspends a stack.

    """
    def run(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

        stack = Stack.objects.get(id=self.stack_id)
        self.stack_name = stack.name

        try:
            status = self.suspend_stack(stack)
        except Exception as e:
            error_msg = "Error suspending stack [%s]: %s" % (
                self.stack_name,
                str(e))
            logger.error(error_msg)
            status = SUSPEND_FAILED
        else:
            error_msg = ""

        # The suspender doesn't check task results, so just save status in the
        # database.
        stack_data = {
            'error_msg': error_msg,
            'status': status,
        }

        # Set the delete_by value based on the delete_age value
        stack_data['delete_by'] = timezone.now() + timezone.timedelta(
            seconds=stack.delete_age)

        self.update_stack(stack_data)

    def suspend_stack(self, stack):
        provider = Provider.init(stack.provider)
        provider_stack = provider.get_stack(stack.name)

        if provider_stack["status"] in UP_STATES + (SUSPEND_FAILED,):
            if (stack.hook_script and
                    stack.hook_events and
                    isinstance(stack.hook_events, dict) and
                    stack.hook_events.get("suspend", False)):
                try:
                    # If there's a suspend hook, execute it.
                    logger.info("Fetching pre-suspend hook [%s] for stack "
                                "[%s]." % (stack.hook_script, stack.ip))
                    script = read_from_contentstore(stack.course_id,
                                                    stack.hook_script)
                    logger.info("SSHing into stack [%s] at [%s]."
                                % (stack.name, stack.ip))
                    ssh = ssh_to(stack.user, stack.ip, stack.key)
                    logger.info("Executing pre-suspend hook for stack [%s]."
                                % stack.name)
                    remote_exec(ssh, script, params="suspend")
                except Exception as e:
                    # We don't fail, as the user may have inadvertently broken
                    # the stack.
                    error_msg = str(e)
                    logger.error("Error running pre-suspend hook for stack "
                                 "[%s]: %s" % (stack.name, error_msg))
                finally:
                    try:
                        ssh.close()
                    except Exception:
                        pass

            # Suspend stack
            logger.info("Suspending stack [%s]." % stack.name)
            provider_stack = provider.suspend_stack(stack.name)
        else:
            logger.error("Cannot suspend stack with status [%s]." %
                         provider_stack["status"])

        return provider_stack["status"]


class DeleteStackTask(HastexoTask):
    """
    Deletes a stack.

    """
    def run(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

        stack = Stack.objects.get(id=self.stack_id)
        self.stack_name = stack.name

        try:
            status = self.delete_stack(stack)
        except Exception as e:
            status = DELETE_FAILED
            provider = stack.provider
            error_msg = "Error deleting stack [%s]: %s" % (
                self.stack_name,
                str(e))
            logger.error(error_msg)
        else:
            provider = ""
            error_msg = ""

        # The reaper doesn't check task results, so just save status in the
        # database.
        stack_data = {
            'status': status,
            'provider': provider,
            'error_msg': error_msg,
        }
        self.update_stack(stack_data)

    def delete_stack(self, stack):
        """
        Delete the stack.

        """
        settings = get_xblock_settings()
        attempts = settings.get("delete_attempts", 3)
        provider = Provider.init(stack.provider)
        provider_stack = provider.get_stack(stack.name)
        attempt = 0

        while (provider_stack["status"] != DELETE_COMPLETE and
               attempt < attempts):
            if attempt:
                self.sleep()

            if provider_stack["status"] != DELETE_IN_PROGRESS:
                logger.info("Attempt [%d] to delete stack [%s]." % (
                    attempt, stack.name))

                # Execute the pre-delete hook.
                if (stack.hook_script and
                        stack.hook_events and
                        isinstance(stack.hook_events, dict) and
                        stack.hook_events.get("delete", False)):
                    try:
                        # We need the stack to be up in order to execute the
                        # pre-delete hook.
                        if provider_stack["status"] == SUSPEND_COMPLETE:
                            provider_stack = provider.resume_stack(
                                stack.name)
                        elif provider_stack["status"] not in UP_STATES:
                            raise Exception("Invalid stack status [%s]." %
                                            provider_stack["status"])
                    except Exception as e:
                        # We don't fail, as deleting the stack is more
                        # important than running the pre-delete hook
                        # successfully.
                        logger.error("Could not resume stack [%s] for "
                                     "pre-delete hook: %s" % (stack.name,
                                                              str(e)))
                    else:
                        logger.info("Executing pre-delete hook for stack [%s] "
                                    "at [%s]." % (stack.name, stack.ip))

                        try:
                            script = read_from_contentstore(stack.course_id,
                                                            stack.hook_script)
                            ssh = ssh_to(stack.user, stack.ip, stack.key)
                            remote_exec(ssh, script, params="delete")
                        except Exception as e:
                            # Again, we don't fail, as deleting the stack is
                            # paramount.
                            logger.error("Could not execute pre-delete hook "
                                         "for stack [%s]: %s" %
                                         (stack.name, str(e)))
                        finally:
                            ssh.close()

                try:
                    provider_stack = provider.delete_stack(stack.name)
                except SoftTimeLimitExceeded:
                    # Retry on any exception except a timeout.
                    raise
                except Exception as e:
                    logger.error("Failed to delete stack [%s]: %s" %
                                 (stack.name, str(e)))
                else:
                    break

            attempt += 1

        if attempt == attempts:
            error_msg = ("Failed to delete stack in [%d] attempts." %
                         attempts)
            raise Exception(error_msg)

        return provider_stack["status"]


class CheckStudentProgressTask(HastexoTask):
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
            ssh = ssh_to(self.stack_user_name,
                         self.stack_ip,
                         self.stack_key)

            # Run tests on the stack
            res = self.run_tests(ssh)
        except (RemoteExecTimeout, SoftTimeLimitExceeded):
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
            try:
                remote_exec(ssh, test, reuse_sftp=sftp)
            except RemoteExecException as e:
                msg = e.args[0]
                hint = msg.decode() if isinstance(msg, bytes) else str(msg)
                if hint:
                    errors.append(hint)
            else:
                score += 1

        sftp.close()

        return {
            'status': 'CHECK_PROGRESS_COMPLETE',
            'pass': score,
            'total': len(self.tests),
            'errors': errors
        }
