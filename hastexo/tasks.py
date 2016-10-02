import time
import os
import paramiko
import uuid
import re

from celery import Task
from celery.utils.log import get_task_logger
from heatclient.exc import HTTPNotFound

from .heat import HeatWrapper
from .swift import SwiftWrapper


class LaunchStackTask(Task):
    """
    Launch, or if it already exists and is suspended, resume a stack for the
    user.

    """
    def run(self, configuration, stack_name, stack_template, stack_user, auth_url, **kwargs):
        """
        Run the celery task.

        """
        logger = get_task_logger(__name__)
        timeouts = configuration.get('task_timeouts')
        status = None
        verify_status = None
        error_msg = None
        stack = None
        stack_ip = None

        # Get the Heat client
        heat = self.get_heat_client(auth_url, **kwargs)

        # Launch the stack and wait for it to complete.
        (status, error_msg, stack) = self.launch_stack(configuration, logger, timeouts, heat, stack_name, stack_template)

        # If launch completed successfully, wait for provisioning, collect
        # its IP address, and save the private key.
        if status == 'CREATE_COMPLETE' or status == 'RESUME_COMPLETE':
            (verify_status, error_msg, stack_ip) = self.verify_stack(configuration, logger, timeouts, stack, stack_name, stack_user)

        # Roll back in case of failure: if it's a failure during creation,
        # delete the stack.  If it's a failure to resume, suspend it.
        if (status == 'CREATE_FAILED'
            or (status == 'CREATE_COMPLETE' and verify_status != 'VERIFY_COMPLETE')):
            logger.debug("Deleting failed stack [%s]" % stack.id)
            heat.stacks.delete(stack_id=stack.id)
            status = 'CREATE_FAILED'
        elif (status == 'RESUME_FAILED'
              or (status == 'RESUME_COMPLETE' and verify_status != 'VERIFY_COMPLETE')):
            logger.debug("Suspending failed stack [%s]" % stack.id)
            heat.actions.suspend(stack_id=stack.id)
            status = 'RESUME_FAILED'

        return {
            'status': status,
            'error_msg': error_msg,
            'ip': stack_ip,
            'user': stack_user,
            'key': stack_name
        }

    def get_heat_client(self, auth_url, **kwargs):
        return HeatWrapper().get_client(auth_url, **kwargs)

    def launch_stack(self, configuration, logger, timeouts, heat, stack_name, stack_template):
        """
        Launch the user stack, either by creating or resuming it.

        """
        status = None
        error_msg = None
        stack = None

        logger.debug("Launching stack [%s]." % stack_name)

        # Create the stack if it doesn't exist, resume it if it's suspended.
        try:
            stack = heat.stacks.get(stack_id=stack_name)
        except HTTPNotFound:
            logger.debug("Stack [%s] doesn't exist.  Creating it." % stack_name)
            res = heat.stacks.create(stack_name=stack_name, template=stack_template)
            stack_id = res['stack']['id']
            stack = heat.stacks.get(stack_id=stack_id)

        status = stack.stack_status

        # If stack is undergoing a change of state, wait until it finishes.
        retry = 0
        while 'IN_PROGRESS' in status:
            if retry:
                time.sleep(timeouts.get('sleep'))
            try:
                stack = heat.stacks.get(stack_id=stack.id)
            except HTTPNotFound:
                logger.debug("Stack [%s] disappeared during change of state. Re-creating it." % stack_name)
                res = heat.stacks.create(stack_name=stack_name, template=stack_template)
                stack_id = res['stack']['id']
                stack = heat.stacks.get(stack_id=stack_id)

            status = stack.stack_status
            retry += 1
            if retry >= timeouts.get('retries'):
                status_prefix = re.sub('_IN_PROGRESS$', '', status)
                status = '%s_FAILED' % status_prefix
                logger.debug("Stack [%s] state change [%s] took too long." % (stack_name, status))

        # If stack is suspended, resume it.
        if status == 'SUSPEND_COMPLETE':
            logger.debug("Resuming stack [%s]." % stack_name)
            heat.actions.resume(stack_id=stack.id)

            # Wait until resume finishes.
            retry = 0
            while ('FAILED' not in status and
                   status != 'RESUME_COMPLETE'):
                if retry:
                    time.sleep(timeouts.get('sleep'))
                try:
                    stack = heat.stacks.get(stack_id=stack.id)
                except HTTPNotFound:
                    status = 'RESUME_FAILED'
                    logger.debug("Stack [%s] disappeared during resume." % stack_name)
                else:
                    status = stack.stack_status
                    retry += 1
                    if retry >= timeouts.get('retries'):
                        status = 'RESUME_FAILED'
                        logger.debug("Stack [%s] resume took too long." % stack_name)

        if status != 'CREATE_COMPLETE' and status != 'RESUME_COMPLETE':
            error_msg = "Stack [%s] launch failed with status [%s]" % (stack_name, status)
            logger.debug(error_msg)
        else:
            logger.debug("Stack [%s] launch successful, with status [%s]." % (stack_name, status))

        return (status, error_msg, stack)

    def verify_stack(self, configuration, logger, timeouts, stack, stack_name, stack_user):
        """
        Check that the stack has a public IP address, a private key, and is
        network accessible.  Save its private key, and check that it is
        possible to SSH into the stack using it.

        """
        verify_status = 'VERIFY_COMPLETE'
        error_msg = None
        stack_ip = None
        stack_key = None

        for output in stack.to_dict().get('outputs', []):
            if output['output_key'] == 'public_ip':
                stack_ip = output['output_value']
            elif output['output_key'] == 'private_key':
                stack_key = output['output_value']

        if stack_ip is None or stack_key is None:
            verify_status = 'VERIFY_FAILED'
            error_msg = "Stack [%s] did not provide IP or private key." % stack_name
            logger.debug(error_msg)
        else:
            # Wait until stack is network accessible, but not indefinitely.
            response = 1
            retry = 0
            while response != 0 and retry < timeouts.get('retries'):
                response = os.system("ping -c 1 -W 5 " + stack_ip + " >/dev/null 2>&1")
                retry += 1

            # Consider stack failed if it isn't network accessible.
            if response != 0:
                verify_status = 'VERIFY_FAILED'
                error_msg = "Stack [%s] is not network accessible." % stack_name
                logger.debug(error_msg)
            else:
                # Export the private key.
                key_path = "%s/%s" % (configuration.get('ssh_dir'), stack_name)
                with open(key_path, 'w') as f:
                    f.write(stack_key)

                # Fix permissions so SSH doesn't complain
                os.chmod(key_path, 0600)

                # Upload key, if necessary
                if configuration.get('ssh_upload'):
                    self.upload_key(stack_name, key_path, configuration)

                # Build the SSH command
                ssh_command = "ssh -T -o StrictHostKeyChecking=no -i %s %s@%s exit" % \
                        (key_path, stack_user, stack_ip)

                # Now wait until environment is fully provisioned.  One of the
                # requirements for the Heat template is for it to disallow SSH
                # access to the training user while provisioning is going on.
                response = 1
                retry = 0
                while response != 0 and retry < timeouts.get('retries'):
                    response = os.system(ssh_command)
                    time.sleep(timeouts.get('sleep'))
                    retry += 1

                if response != 0:
                    verify_status = 'VERIFY_FAILED'
                    error_msg = "Stack [%s] provisioning did not complete." % stack_name
                    logger.debug(error_msg)
                else:
                    logger.debug("Stack [%s] verification successful." % stack_name)

        return (verify_status, error_msg, stack_ip)

    def upload_key(self, key, key_path, configuration):
        swift = SwiftWrapper(configuration)
        swift.upload_key(key, key_path)


class SuspendStackTask(Task):
    """
    Suspend a stack.

    """
    def run(self, configuration, stack_name, auth_url, **kwargs):
        """
        Suspend a stack.  There is no return value, as nobody will check for it.

        """
        logger = get_task_logger(__name__)
        timeouts = configuration.get('timeouts')

        # Get the Heat client
        heat = self.get_heat_client(auth_url, **kwargs)

        # Suspend the stack.
        self.suspend_stack(logger, timeouts, heat, stack_name)

    def get_heat_client(self, auth_url, **kwargs):
        return HeatWrapper().get_client(auth_url, **kwargs)

    def suspend_stack(self, logger, timeouts, heat, stack_name):
        """
        Suspend the stack.
        """

        # Find the stack.  If it doesn't exist, there's nothing to do here.
        try:
            stack = heat.stacks.get(stack_id=stack_name)
        except HTTPNotFound:
            error_msg = "Stack [%s] doesn't exist." % stack_name
            logger.debug(error_msg)
            return

        status = stack.stack_status

        # If the stack is broken, already suspended, or in the process of, there's
        # nothing to do here.
        if ('FAILED' in status or
             status == 'SUSPEND_COMPLETE' or
             status == 'SUSPEND_IN_PROGRESS'):
            return

        # If the stack is undergoing some other change of state, wait for it to
        # complete.
        retry = 0
        while 'IN_PROGRESS' in status:
            if retry:
                time.sleep(timeouts.get('sleep'))
            try:
                stack = heat.stacks.get(stack_id=stack.id)
            except HTTPNotFound:
                status = 'SUSPEND_FAILED'
                error_msg = "Stack disappeared during state change [%s]." % status
                logger.debug(error_msg)
            else:
                status = stack.stack_status
                retry += 1
                if retry >= timeouts.get('retries'):
                    status = 'SUSPEND_FAILED'
                    error_msg = "Stack [%s] state change [%s] took too long." % (stack_name, status)
                    logger.debug(error_msg)

        # At this point, the stack has been verified to be running.  So suspend it.
        if 'FAILED' not in status:
            heat.actions.suspend(stack_id=stack_name)


class CheckStudentProgressTask(Task):
    """
    Check student progress by running a set of scripts via SSH.

    """
    def run(self, configuration, tests, stack_ip, stack_name, stack_user):
        # Open SSH connection to the public facing node
        ssh = self.open_ssh_connection(configuration, stack_name, stack_user, stack_ip)

        # Run tests on the stack
        res = self.run_tests(ssh, tests)

        # Close the connection
        ssh.close()

        return res

    def run_tests(self, ssh, tests):
        sftp = ssh.open_sftp()

        # Write scripts out, run them, and keep score.
        score = 0
        for test in tests:
            # Generate a temporary filename
            script = '/tmp/.%s' % uuid.uuid4()

            # Open the file remotely and write the script out to it.
            f = sftp.open(script, 'w')
            f.write(test)
            f.close()

            # Make it executable and run it.
            sftp.chmod(script, 0775)
            stdin, stdout, stderr = ssh.exec_command(script)
            retval = stdout.channel.recv_exit_status()
            if retval == 0:
                score += 1

            # Remove the script
            sftp.remove(script)

        return {
            'status': 'COMPLETE',
            'pass': score,
            'total': len(tests)
        }

    def open_ssh_connection(self, configuration, stack_name, stack_user, stack_ip):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        key_filename = "%s/%s" % (configuration.get('ssh_dir'), stack_name)
        if not os.path.exists(key_filename):
            # Download key, if necessary
            if configuration.get('ssh_upload', False):
                self.download_key(stack_name, key_filename, configuration)
            else:
                raise Exception

        ssh.connect(stack_ip, username=stack_user, key_filename=key_filename)

        return ssh

    def download_key(self, key, key_path, configuration):
        swift = SwiftWrapper(configuration)
        swift.download_key(key, key_path)
