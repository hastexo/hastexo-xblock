"""
Asynchronous Viaduct tasks.
"""

import time

from celery.task import task
from celery.utils.log import get_task_logger

from keystoneclient.v2_0.client import Client as kclient
from heatclient.v1.client import Client as hclient
from heatclient import exc

logger = get_task_logger(__name__)

@task()
def launch_or_resume_user_stack(user_id, os_auth_url, os_username, os_password,
        os_tenant_name, os_heat_template):
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
        stack = heat.stacks.get(stack_id=user_id)
    except exc.HTTPNotFound:
        logger.debug("Stack doesn't exist.  Creating it.")
        res = heat.stacks.create(stack_name=user_id, template=os_heat_template)
        stack_id = res['stack']['id']
        stack = heat.stacks.get(stack_id=stack_id)

    status = stack.stack_status

    # If stack is suspended, resume it.
    if status == "SUSPEND_IN_PROGRESS" or status == "SUSPEND_COMPLETE":
        logger.debug("Resuming stack.")
        heat.actions.resume(stack_id=stack.id)

    # Poll at 5 second intervals until the stack is ready
    while (status != 'CREATE_COMPLETE' and
           status != 'RESUME_COMPLETE' and
           status != 'CREATE_FAILED' and
           status != 'RESUME_FAILED'):
        time.sleep(5)
        stack = heat.stacks.get(stack_id=stack.id)
        status = stack.stack_status

    ip = None
    if status == 'CREATE_COMPLETE' or status == 'RESUME_COMPLETE':
        for output in stack.to_dict().get('outputs', []):
            if output['output_key'] == 'public_ip':
                ip = output['output_value']
        error_msg = None
        logger.debug("Stack creation successful.")
    else:
        error_msg = "Stack creation failed."
        logger.debug("Stack creation failed.")

    return {
        'status': status,
        'ip': ip,
        'error_msg': error_msg
    }

@task()
def suspend_user_stack(user_id, os_auth_url, os_username, os_password,
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
        stack = heat.actions.get(stack_id=user_id)
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
    heat.actions.suspend(stack_id=user_id)
