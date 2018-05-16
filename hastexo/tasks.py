import time
import os
import uuid
import paramiko

from celery import Task
from celery.utils.log import get_task_logger
from celery.exceptions import SoftTimeLimitExceeded
from heatclient.exc import HTTPNotFound
from io import StringIO

from .heat import HeatWrapper
from .nova import NovaWrapper

logger = get_task_logger(__name__)


class LaunchStackFailed(Exception):
    status = ""
    error_msg = ""
    suspend = False
    delete = False

    def __init__(self, status, error_msg, cleanup=0):
        super(LaunchStackFailed, self).__init__()

        self.status = status
        self.error_msg = error_msg

        if cleanup == 1:
            self.suspend = True
        elif cleanup == 2:
            self.delete = True


class LaunchStackTask(Task):
    """
    Launch, or if it already exists and is suspended, resume a stack for the
    user.

    """

    def run(self,
            configuration,
            stack_run,
            stack_name,
            stack_template,
            stack_user,
            reset=False):
        """
        Run the celery task.

        """
        self.configuration = configuration
        self.stack_run = stack_run
        self.stack_name = stack_name
        self.stack_template = stack_template
        self.stack_user = stack_user
        self.reset = reset
        self.heat_client = self.get_heat_client()
        task_timeouts = configuration.get('task_timeouts', {})
        self.sleep_seconds = task_timeouts.get('sleep', 5)

        try:
            # Launch the stack and wait for it to complete.
            stack_data = self.launch_stack()
        except LaunchStackFailed as e:
            logger.error(e.error_msg)
            stack_data = {
                'status': e.status,
                'error_msg': e.error_msg,
                'ip': None,
                'user': "",
                'key': "",
                'password': ""
            }

            # Roll back in case of failure
            if e.delete:
                logger.error("Deleting unsuccessfully "
                             "created stack [%s]." % self.stack_name)
                self.heat_client.stacks.delete(stack_id=self.stack_name)
            elif e.suspend:
                logger.error("Suspending unsuccessfully "
                             "resumed stack [%s]." % self.stack_name)
                self.heat_client.actions.suspend(stack_id=self.stack_name)

        return stack_data

    def sleep(self):
        time.sleep(self.sleep_seconds)

    def get_heat_client(self):
        return HeatWrapper(**self.configuration).get_client()

    def get_nova_client(self):
        return NovaWrapper(**self.configuration).get_client()

    def launch_stack(self):
        """
        Launch the user stack, either by creating or resuming it.  If a reset
        is requested, delete the stack and recreate it.

        """
        status = ""
        error_msg = ""
        stack = None
        was_resumed = False

        logger.info("Launching stack [%s]." % self.stack_name)

        # Check if the stack exists
        try:
            stack = self.heat_client.stacks.get(stack_id=self.stack_name)
        except HTTPNotFound:
            logger.info("Stack [%s] doesn't exist." % self.stack_name)
            status = 'DELETE_COMPLETE'
        except SoftTimeLimitExceeded:
            error_msg = "Timeout fetching stack [%s] information." % (
                self.stack_name)
            raise LaunchStackFailed("LAUNCH_TIMEOUT", error_msg)
        else:
            status = stack.stack_status

        # If stack is undergoing a change of state, wait until it finishes.
        try:
            while 'IN_PROGRESS' in status:
                try:
                    # Sleep to avoid throttling.
                    self.sleep()

                    stack = self.heat_client.stacks.get(stack_id=stack.id)
                except HTTPNotFound:
                    status = 'DELETE_COMPLETE'
                else:
                    status = stack.stack_status
        except SoftTimeLimitExceeded:
            error_msg = "Timeout waiting for stack [%s] state change." % (
                self.stack_name)
            raise LaunchStackFailed("LAUNCH_TIMEOUT", error_msg)

        # Delete the stack if this is a reset request.
        try:
            if self.reset and status != 'DELETE_COMPLETE':
                # Sleep to avoid throttling.
                self.sleep()

                logger.info("Resetting stack [%s]." % self.stack_name)
                status = self.reset_stack(stack)
        except SoftTimeLimitExceeded:
            error_msg = "Timeout resetting stack [%s]." % self.stack_name
            raise LaunchStackFailed("LAUNCH_TIMEOUT", error_msg)

        # If stack doesn't exist, create it.
        try:
            if status == 'DELETE_COMPLETE':
                # Sleep to avoid throttling.
                self.sleep()

                logger.info("Creating stack [%s]." % self.stack_name)
                stack = self.create_stack()
                status = stack.stack_status
        except SoftTimeLimitExceeded:
            error_msg = "Timeout creating stack [%s]." % self.stack_name
            raise LaunchStackFailed("LAUNCH_TIMEOUT", error_msg, 2)

        # If stack is suspended, resume it.
        try:
            if status == 'SUSPEND_COMPLETE':
                # Store the fact the stack was resumed
                was_resumed = True

                # Sleep to avoid throttling.
                self.sleep()

                logger.info("Resuming stack [%s]." % self.stack_name)
                status = self.resume_stack(stack)
        except SoftTimeLimitExceeded:
            error_msg = "Timeout resuming stack [%s]." % self.stack_name
            raise LaunchStackFailed("LAUNCH_TIMEOUT", error_msg, 1)

        # Launch completed successfully.  Wait for provisioning, collect
        # its IP address, and save the private key.
        try:
            check_data = self.check_stack(stack, was_resumed)
        except SoftTimeLimitExceeded:
            if was_resumed:
                cleanup = 1
            else:
                cleanup = 2

            error_msg = "Timeout verifying stack [%s]." % self.stack_name
            raise LaunchStackFailed("LAUNCH_TIMEOUT", error_msg, cleanup)

        stack_data = {
            'status': status,
            'error_msg': error_msg,
            'ip': check_data["ip"],
            'user': self.stack_user,
            'key': check_data["key"],
            'password': check_data["password"]
        }

        return stack_data

    def create_stack(self):
        res = self.heat_client.stacks.create(
            stack_name=self.stack_name,
            template=self.stack_template,
            parameters={'run': self.stack_run}
        )
        stack_id = res['stack']['id']

        # Sleep to avoid throttling.
        self.sleep()

        stack = self.heat_client.stacks.get(stack_id=stack_id)
        status = stack.stack_status

        # Wait for stack creation
        while 'IN_PROGRESS' in status:
            self.sleep()

            try:
                stack = self.heat_client.stacks.get(stack_id=stack.id)
            except HTTPNotFound:
                error_msg = "Stack [%s] disappeared during creation. " % (
                    self.stack_name)
                raise LaunchStackFailed("CREATE_FAILED", error_msg)

            status = stack.stack_status

        if 'FAILED' in status:
            error_msg = "Failure creating stack [%s]" % self.stack_name
            raise LaunchStackFailed("CREATE_FAILED", error_msg, 2)

        return stack

    def reset_stack(self, stack):
        self.heat_client.stacks.delete(stack_id=stack.id)
        status = 'DELETE_IN_PROGRESS'

        # Wait until delete finishes.
        while ('FAILED' not in status and
               status != 'DELETE_COMPLETE'):
            self.sleep()

            try:
                stack = self.heat_client.stacks.get(stack_id=stack.id)
            except HTTPNotFound:
                status = 'DELETE_COMPLETE'
            else:
                status = stack.stack_status

        if 'FAILED' in status:
            error_msg = "Failure resetting stack [%s]" % self.stack_name
            raise LaunchStackFailed("CREATE_FAILED", error_msg)

        return status

    def resume_stack(self, stack):
        self.heat_client.actions.resume(stack_id=stack.id)
        status = 'RESUME_IN_PROGRESS'

        # Wait until resume finishes.
        while ('FAILED' not in status and
               status != 'RESUME_COMPLETE'):
            self.sleep()

            try:
                stack = self.heat_client.stacks.get(stack_id=stack.id)
            except HTTPNotFound:
                error_msg = "Stack [%s] disappeared during resume. " % (
                    self.stack_name)
                raise LaunchStackFailed("RESUME_FAILED", error_msg)
            else:
                status = stack.stack_status

        if 'FAILED' in status:
            error_msg = "Failure resuming stack [%s]" % self.stack_name
            raise LaunchStackFailed("RESUME_FAILED", error_msg, 1)

        return status

    def check_stack(self, stack, was_resumed):
        """
        Fetch stack outputs, check that the stack has a public IP address, a
        private key, and is network accessible after rebooting any servers.
        Save its private key, and check that it is possible to SSH into the
        stack using it.

        """
        stack_ip = None
        stack_key = ""
        stack_password = ""
        reboot_on_resume = None

        logger.debug("Verifying stack [%s] " % self.stack_name)

        # Fetch stack outputs
        for output in stack.to_dict().get('outputs', []):
            if output['output_key'] == 'public_ip':
                stack_ip = output['output_value']
                logger.debug("Found IP [%s] for stack [%s]" % (
                    stack_ip, self.stack_name))
            elif output['output_key'] == 'private_key':
                stack_key = output['output_value']
                logger.debug("Found key for stack [%s]" % (self.stack_name))
            elif output['output_key'] == 'password':
                stack_password = output['output_value']
                logger.debug("Found password for stack [%s]" % (
                    self.stack_name))
            elif output['output_key'] == 'reboot_on_resume':
                reboot_on_resume = output['output_value']
                logger.debug("Found servers to reboot on resume "
                             "for stack [%s]" % (self.stack_name))

        if stack_ip is None or not stack_key:
            if was_resumed:
                error_status = 'SUSPEND_FAILED'
                cleanup = 1
            else:
                error_status = 'CREATE_FAILED'
                cleanup = 2

            error_msg = ("Stack [%s] did not provide "
                         "IP or private key." % self.stack_name)
            raise LaunchStackFailed(error_status, error_msg, cleanup)

        # Reboot servers, if necessary
        if (was_resumed and
                reboot_on_resume is not None and
                isinstance(reboot_on_resume, list)):
            nova = self.get_nova_client()

            for server in reboot_on_resume:
                logger.info("Hard rebooting server [%s]" % server)
                nova.servers.reboot(server, 'HARD')

        # Wait until stack is network accessible
        logger.info("Waiting for stack [%s] "
                    "to become network accessible "
                    "at [%s]" % (self.stack_name, stack_ip))

        ping_command = "ping -c 1 -W %d %s >/dev/null 2>&1" % (
            self.sleep_seconds, stack_ip)
        while os.system(ping_command) != 0:
            self.sleep()

        # Now wait until environment is fully provisioned.  One of the
        # requirements for the Heat template is for it to disallow SSH
        # access to the training user while provisioning is going on.
        logger.info("Checking SSH connection "
                    "for stack [%s] at [%s]" % (self.stack_name, stack_ip))

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = paramiko.RSAKey.from_private_key(StringIO(stack_key))
        connected = False
        while not connected:
            try:
                ssh.connect(stack_ip, username=self.stack_user, pkey=pkey)
            except (paramiko.ssh_exception.AuthenticationException,
                    paramiko.ssh_exception.SSHException,
                    paramiko.ssh_exception.NoValidConnectionsError):
                self.sleep()
            else:
                ssh.close()
                connected = True

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

    def run(self, configuration, tests, stack_ip, stack_user, stack_key):
        self.configuration = configuration
        self.tests = tests
        self.stack_ip = stack_ip
        self.stack_user = stack_user
        self.stack_key = stack_key

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
        for test in self.tests:
            # Generate a temporary filename
            script = '/tmp/.%s' % uuid.uuid4()

            # Open the file remotely and write the script out to it.
            f = sftp.open(script, 'w')
            f.write(test)
            f.close()

            # Make it executable and run it.
            sftp.chmod(script, 0o775)
            _, stdout, _ = ssh.exec_command(script)
            retval = stdout.channel.recv_exit_status()
            if retval == 0:
                score += 1

            # Remove the script
            sftp.remove(script)

        return {
            'status': 'CHECK_PROGRESS_COMPLETE',
            'pass': score,
            'total': len(self.tests)
        }

    def open_ssh_connection(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        pkey = paramiko.RSAKey.from_private_key(StringIO(self.stack_key))

        ssh.connect(self.stack_ip, username=self.stack_user, pkey=pkey)

        return ssh
