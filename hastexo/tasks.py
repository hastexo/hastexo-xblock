"""
Asynchronous tasks.
"""

import time
import os

from celery.task import task
from celery.utils.log import get_task_logger

from keystoneclient.v2_0.client import Client as kclient
from heatclient.v1.client import Client as hclient
from heatclient import exc

logger = get_task_logger(__name__)

@task()
def launch_or_resume_user_stack(stack_name, stack_user_name, os_auth_url,
        os_username, os_password, os_tenant_name, os_heat_template):
    """
    Launch, or if it already exists and is suspended, resume a stack for the
    user.
    """
    logger.debug("Launching or resuming user stack.")

    # Authenticate with Keystone
    keystone = kclient(auth_url=os_auth_url, username=os_username,
        password=os_password, tenant_name=os_tenant_name)

    # Get the Heat endpoint from the Keystone catalog
    heat_endpoint = keystone.service_catalog.url_for(service_type='orchestration',
        endpoint_type='publicURL')

    # Instantiate the Heat client
    heat = hclient(endpoint=heat_endpoint, token=keystone.auth_token)

    # Create the stack if it doesn't exist, resume it if it's suspended.
    try:
        stack = heat.stacks.get(stack_id=stack_name)
    except exc.HTTPNotFound:
        logger.debug("Stack doesn't exist.  Creating it.")
        res = heat.stacks.create(stack_name=stack_name, template=os_heat_template)
        stack_id = res['stack']['id']
        stack = heat.stacks.get(stack_id=stack_id)

    status = stack.stack_status

    # If stack is being suspended, wait.
    while status == "SUSPEND_IN_PROGRESS":
        time.sleep(5)
        stack = heat.stacks.get(stack_id=stack.id)
        status = stack.stack_status

    # If stack is suspended, resume it.
    if status == "SUSPEND_COMPLETE":
        logger.debug("Resuming stack.")
        heat.actions.resume(stack_id=stack.id)

    # Wait until stack is ready (or failed).
    while (status != 'CREATE_COMPLETE' and
           status != 'RESUME_COMPLETE' and
           status != 'CREATE_FAILED' and
           status != 'RESUME_FAILED'):
        time.sleep(5)
        stack = heat.stacks.get(stack_id=stack.id)
        status = stack.stack_status

    ip = None
    key = None
    if status == 'CREATE_COMPLETE' or status == 'RESUME_COMPLETE':
        for output in stack.to_dict().get('outputs', []):
            if output['output_key'] == 'public_ip':
                ip = output['output_value']
            elif output['output_key'] == 'private_key':
                key = output['output_value']

        if ip is None or key is None:
            status = 'CREATE_FAILED'
            error_msg = "Stack did not provide enough data."
            logger.debug(error_msg)
        else:
            # Wait until stack is network accessible, but not indefinitely.
            response = 1
            count = 0
            while response != 0 and count < 120:
                response = os.system("ping -c 1 -W 5 " + ip + " >/dev/null 2>&1")
                count += 1

            # Consider stack failed if it isn't network accessible.
            if response != 0:
                status = 'CREATE_FAILED'
                error_msg = "Stack is not network accessible."
                logger.debug(error_msg)
            else:
                # Export the private key.
                key_path = "/edx/var/edxapp/terminal_users/ANONYMOUS/.ssh/%s" % stack_name
                with open(key_path, 'w') as f:
                    f.write(key)

                # Fix permissions so SSH doesn't complain
                os.chmod(key_path, 0600)

                # Build the SSH command
                ssh_command = "ssh -T -o StrictHostKeyChecking=no -i %s %s@%s exit" % \
                        (key_path, stack_user_name, ip)

                # Now wait until environment is fully provisioned.  One of the
                # requirements for the Heat template is for it to disallow SSH
                # access to the training user while provisioning is going on.
                response = 1
                count = 0
                while response != 0 and count < 120:
                    response = os.system(ssh_command)
                    time.sleep(5)
                    count += 1

                if response != 0:
                    status = 'CREATE_FAILED'
                    error_msg = "Stack provisioning did not complete."
                    logger.debug(error_msg)
                else:
                    error_msg = None
                    logger.debug("Stack creation successful.")
    else:
        error_msg = "Stack creation failed."
        logger.debug(error_msg)

    return {
        'status': status,
        'ip': ip,
        'user': stack_user_name,
        'key': stack_name,
        'error_msg': error_msg
    }

@task()
def suspend_user_stack(stack_name, os_auth_url, os_username, os_password,
        os_tenant_name):
    """
    Suspend a stack.
    """
    # Authenticate with Keystone
    keystone = kclient(auth_url=os_auth_url, username=os_username,
        password=os_password, tenant_name=os_tenant_name)

    # Get the Heat endpoint from the Keystone catalog
    heat_endpoint = keystone.service_catalog.url_for(service_type='orchestration',
        endpoint_type='publicURL')

    # Instantiate the Heat client
    heat = hclient(endpoint=heat_endpoint, token=keystone.auth_token)

    # Find the stack.  If it doesn't exist, there's nothing to do here.
    try:
        stack = heat.stacks.get(stack_id=stack_name)
    except exc.HTTPNotFound:
        logger.debug("Stack doesn't exist.")
        return

    status = stack.stack_status

    # If the stack is already suspended, or in the process of, there's nothing
    # to do here.
    if (status == 'SUSPEND_COMPLETE' or
        status == 'SUSPEND_IN_PROGRESS'):
        return

    # If the stack is undergoing some other change of state, wait for it to
    # complete.
    while (status != 'CREATE_COMPLETE' and
           status != 'RESUME_COMPLETE' and
           status != 'CREATE_FAILED' and
           status != 'RESUME_FAILED'):
        time.sleep(5)
        stack = heat.stacks.get(stack_id=stack.id)
        status = stack.stack_status

    # If the stack is failed, there's also nothing to do here.
    if (status == 'CREATE_FAILED' or
        status == 'RESUME_FAILED'):
        logger.debug("Stack is failed.")
        return

    # At this point, the stack has been verified to be running.  So suspend it.
    heat.actions.suspend(stack_id=stack_name)
