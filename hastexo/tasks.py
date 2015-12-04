"""
Asynchronous tasks.
"""

import time
import os
import paramiko
import uuid

from celery.task import task
from celery.utils.log import get_task_logger

from keystoneclient.auth.identity import v2 as v2_auth
from keystoneclient.auth.identity import v3 as v3_auth
from keystoneclient import discover
from keystoneclient.openstack.common.apiclient import exceptions as ks_exc
from keystoneclient import session as kssession
from heatclient import client as heat_client
from heatclient import exc
from six.moves.urllib import parse as urlparse

logger = get_task_logger(__name__)

def get_keystone_auth(session, auth_url, **kwargs):
    """
    Figure out whether to use v2 or v3 of the Keystone API, and return the auth
    object.

    This function is based, with minor changes, on the official OpenStack Heat
    client's shell implementation.  Specifically,
    python-heatclient/heatclient/shell.py.
    """
    v2_auth_url = None
    v3_auth_url = None
    try:
        ks_discover = discover.Discover(session=session, auth_url=auth_url)
        v2_auth_url = ks_discover.url_for('2.0')
        v3_auth_url = ks_discover.url_for('3.0')
    except ks_exc.ClientException:
        # If discovery is not supported, parse version out of the auth URL.
        url_parts = urlparse.urlparse(auth_url)
        (scheme, netloc, path, params, query, fragment) = url_parts
        path = path.lower()
        if path.startswith('/v3'):
            v3_auth_url = auth_url
        elif path.startswith('/v2'):
            v2_auth_url = auth_url
        else:
            raise exc.CommandError('Unable to determine Keystone version.')

    auth = None
    if v3_auth_url and v2_auth_url:
        # Both v2 and v3 are supported. Use v3 only if domain information is
        # provided.
        user_domain_name = kwargs.get('user_domain_name', None)
        user_domain_id = kwargs.get('user_domain_id', None)
        project_domain_name = kwargs.get('project_domain_name', None)
        project_domain_id = kwargs.get('project_domain_id', None)

        if (user_domain_name or user_domain_id or project_domain_name or
                project_domain_id):
            auth = get_keystone_v3_auth(v3_auth_url, **kwargs)
        else:
            auth = get_keystone_v2_auth(v2_auth_url, **kwargs)
    elif v3_auth_url:
        auth = get_keystone_v3_auth(v3_auth_url, **kwargs)
    elif v2_auth_url:
        auth = get_keystone_v2_auth(v2_auth_url, **kwargs)
    else:
        raise exc.CommandError('Unable to determine Keystone version.')

    return auth

def get_keystone_v3_auth(v3_auth_url, **kwargs):
    auth_token = kwargs.pop('auth_token', None)
    if auth_token:
        return v3_auth.Token(v3_auth_url, auth_token)
    else:
        return v3_auth.Password(v3_auth_url, **kwargs)

def get_keystone_v2_auth(v2_auth_url, **kwargs):
    auth_token = kwargs.pop('auth_token', None)
    tenant_id = kwargs.get('project_id', None)
    tenant_name = kwargs.get('project_name', None)
    if auth_token:
        return v2_auth.Token(v2_auth_url, auth_token,
                             tenant_id=tenant_id,
                             tenant_name=tenant_name)
    else:
        username=kwargs.get('username', None)
        password=kwargs.get('password', None)
        return v2_auth.Password(v2_auth_url,
                                username=username,
                                password=password,
                                tenant_id=tenant_id,
                                tenant_name=tenant_name)

def get_heat_client(auth_url, **kwargs):
    service_type = 'orchestration'
    endpoint_type = 'publicURL'
    api_version = '1'
    region_name = kwargs.pop('region_name', None)
    username = kwargs.get('username', None)
    password = kwargs.get('password', None)

    # Authenticate with Keystone
    keystone_session = kssession.Session()
    keystone_auth = get_keystone_auth(keystone_session, auth_url, **kwargs)

    # Get the Heat endpoint
    endpoint = keystone_auth.get_endpoint(keystone_session,
                                          service_type=service_type,
                                          interface=endpoint_type,
                                          region_name=region_name)

    # Initiate the Heat client
    heat_kwargs = {'auth_url': auth_url,
                   'session': keystone_session,
                   'auth': keystone_auth,
                   'service_type': service_type,
                   'endpoint_type': endpoint_type,
                   'region_name': region_name,
                   'username': username,
                   'password': password}
    client = heat_client.Client(api_version, endpoint, **heat_kwargs)

    return client

@task()
def launch_or_resume_user_stack(stack_name, stack_template, stack_user, auth_url, **kwargs):
    """
    Launch, or if it already exists and is suspended, resume a stack for the
    user.
    """
    logger.debug("Launching or resuming user stack.")

    # Get the heat client
    heat = get_heat_client(auth_url, **kwargs)

    # Create the stack if it doesn't exist, resume it if it's suspended.
    try:
        stack = heat.stacks.get(stack_id=stack_name)
    except exc.HTTPNotFound:
        logger.debug("Stack doesn't exist.  Creating it.")
        res = heat.stacks.create(stack_name=stack_name, template=stack_template)
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
                        (key_path, stack_user, ip)

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
        'user': stack_user,
        'key': stack_name,
        'error_msg': error_msg
    }

@task()
def suspend_user_stack(stack_name, auth_url, **kwargs):
    """
    Suspend a stack.
    """
    # Get the heat client
    heat = get_heat_client(auth_url, **kwargs)

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

@task()
def check(tests, stack_ip, stack_name, stack_user):
    """
    Run a set of assessment tests via SSH.
    """
    # Open SSH connection to the public facing node
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key_filename = "/edx/var/edxapp/terminal_users/ANONYMOUS/.ssh/%s" % stack_name
    ssh.connect(stack_ip,
                username=stack_user,
                key_filename=key_filename)
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

    ssh.close()

    return {
        'status': 'COMPLETE',
        'pass': score,
        'total': len(tests)
    }
