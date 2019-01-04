import time

from heatclient.exc import HTTPException, HTTPNotFound
from novaclient.exceptions import ClientException

from .common import (get_xblock_settings,
                     DELETED_STATE, DELETE_IN_PROGRESS_STATE,
                     RESUME_STATE, RESUME_IN_PROGRESS_STATE)
from .openstack import HeatWrapper, NovaWrapper


class ProviderException(Exception):
    error_msg = ""

    def __init__(self, error_msg=""):
        super(ProviderException, self).__init__()
        self.error_msg = error_msg


class Provider(object):
    """
    Base class for provider drivers.

    """
    default_credentials = None
    credentials = None
    name = None
    capacity = None
    template = None
    environment = None
    sleep_seconds = None

    @staticmethod
    def init(name):
        settings = get_xblock_settings()
        task_timeouts = settings.get('task_timeouts', {})
        sleep_seconds = task_timeouts.get('sleep', 5)
        providers = settings.get("providers")
        config = providers.get(name)
        if config and isinstance(config, dict):
            provider_type = config.get("type")
            if provider_type == "openstack" or not provider_type:
                return OpenstackProvider(name, config, sleep_seconds)

    def __init__(self, name, config, sleep):
        self.name = name
        self.sleep_seconds = sleep

        # Get credentials
        if config and isinstance(config, dict):
            credentials = {}
            for key, default in self.default_credentials.iteritems():
                credentials[key] = config.get(key, default)
            self.credentials = credentials
        else:
            error_msg = ("No configuration provided for provider %s" %
                         self.name)
            raise ProviderException(error_msg)

    def set_capacity(self, capacity):
        if capacity in (None, "None"):
            capacity = -1
        else:
            try:
                capacity = int(capacity)
            except (TypeError, ValueError):
                # Invalid capacity: disable the provider
                capacity = 0

        self.capacity = capacity

    def set_template(self, template):
        if not template:
            error_msg = ("No template provided for provider %s" % self.name)
            raise ProviderException(error_msg)

        self.template = template

    def set_environment(self, environment):
        if not environment:
            error_msg = ("No environment provided for provider %s" % self.name)
            raise ProviderException(error_msg)

        self.environment = environment

    def sleep(self):
        time.sleep(self.sleep_seconds)

    def get_stack(self):
        raise NotImplementedError()

    def create_stack(self):
        raise NotImplementedError()

    def delete_stack(self):
        raise NotImplementedError()

    def suspend_stack(self):
        raise NotImplementedError()

    def resume_stack(self):
        raise NotImplementedError()


class OpenstackProvider(Provider):
    """
    OpenStack provider driver.

    """
    default_credentials = {
        "os_auth_url": "",
        "os_auth_token": "",
        "os_username": "",
        "os_password": "",
        "os_user_id": "",
        "os_user_domain_id": "",
        "os_user_domain_name": "",
        "os_project_id": "",
        "os_project_name": "",
        "os_project_domain_id": "",
        "os_project_domain_name": "",
        "os_region_name": ""
    }
    heat_c = None
    nova_c = None

    def __init__(self, provider, config, sleep):
        super(OpenstackProvider, self).__init__(provider, config, sleep)

        self.heat_c = self._get_heat_client()
        self.nova_c = self._get_nova_client()

    def _get_heat_client(self):
        return HeatWrapper(**self.credentials).get_client()

    def _get_nova_client(self):
        return NovaWrapper(**self.credentials).get_client()

    def _get_stack_outputs(self, heat_stack):
        outputs = {}
        for o in getattr(heat_stack, 'outputs', []):
            output_key = o["output_key"]
            output_value = o["output_value"]
            outputs[output_key] = output_value

        return outputs

    def get_stack(self, name):
        try:
            heat_stack = self.heat_c.stacks.get(stack_id=name)
        except HTTPNotFound:
            status = DELETED_STATE
            outputs = {}
        except HTTPException as e:
            error_msg = ("Error retrieving [%s] stack information: %s" %
                         (name, e))
            raise ProviderException(error_msg)
        else:
            status = heat_stack.stack_status
            outputs = self._get_stack_outputs(heat_stack)

        return {"status": status,
                "outputs": outputs}

    def create_stack(self, name, run):
        if not self.template:
            raise ProviderException("Template not set for stack [%s], provider"
                                    " [%s]." % (name, self.name))

        try:
            res = self.heat_c.stacks.create(
                stack_name=name,
                template=self.template,
                environment=self.environment,
                parameters={'run': run}
            )
        except HTTPException as e:
            error_msg = ("Error creating stack [%s]: %s" %
                         (name, e))
            raise ProviderException(error_msg)

        stack_id = res['stack']['id']

        # Sleep to avoid throttling.
        self.sleep()

        try:
            heat_stack = self.heat_c.stacks.get(stack_id=stack_id)
        except HTTPException as e:
            error_msg = ("Error retrieving [%s] stack information: %s" %
                         (name, e))
            raise ProviderException(error_msg)

        status = heat_stack.stack_status

        # Wait for stack creation
        while 'IN_PROGRESS' in status:
            self.sleep()

            try:
                heat_stack = self.heat_c.stacks.get(stack_id=heat_stack.id)
            except HTTPNotFound:
                error_msg = "Stack [%s] disappeared during creation. " % name
                raise ProviderException(error_msg)
            except HTTPException as e:
                error_msg = ("Error retrieving [%s] stack information: %s" %
                             (name, e))
                raise ProviderException(error_msg)

            status = heat_stack.stack_status

        if 'FAILED' in status:
            error_msg = "Failure creating stack [%s]" % name
            raise ProviderException(error_msg)

        return {"status": status,
                "outputs": self._get_stack_outputs(heat_stack)}

    def resume_stack(self, name):
        try:
            self.heat_c.actions.resume(stack_id=name)
        except HTTPException as e:
            error_msg = ("Error resuming stack [%s]: %s" %
                         (name, e))
            raise ProviderException(error_msg)

        status = RESUME_IN_PROGRESS_STATE

        # Wait until resume finishes.
        while ('FAILED' not in status and
               status != RESUME_STATE):
            self.sleep()

            try:
                heat_stack = self.heat_c.stacks.get(
                    stack_id=name)
            except HTTPNotFound:
                error_msg = "Stack [%s] disappeared during resume. " % name
                raise ProviderException(error_msg)
            except HTTPException as e:
                error_msg = ("Error retrieving [%s] stack information: %s" %
                             (name, e))
                raise ProviderException(error_msg)
            else:
                status = heat_stack.stack_status

        if 'FAILED' in status:
            error_msg = "Failure resuming stack [%s]" % name
            raise ProviderException(error_msg)

        outputs = self._get_stack_outputs(heat_stack)

        # Reboot servers, if requested
        reboot_on_resume = outputs.get("reboot_on_resume")
        if (reboot_on_resume is not None and
                isinstance(reboot_on_resume, list)):
            for server in reboot_on_resume:
                try:
                    self.nova_c.servers.reboot(server, 'HARD')
                except ClientException as e:
                    error_msg = ("Error rebooting stack [%s] server [%s]: %s" %
                                 (name, server, e))
                    raise ProviderException(error_msg)

        return {"status": status,
                "outputs": outputs}

    def suspend_stack(self, name):
        try:
            self.heat_c.actions.suspend(stack_id=name)
        except HTTPException as e:
            error_msg = ("Error suspending stack [%s]: %s" %
                         (name, e))
            raise ProviderException(error_msg)

    def delete_stack(self, name, wait=True):
        try:
            self.heat_c.stacks.delete(stack_id=name)
        except HTTPException as e:
            error_msg = ("Error deleting stack [%s]: %s" %
                         (name, e))
            raise ProviderException(error_msg)

        status = DELETE_IN_PROGRESS_STATE

        # Wait until delete finishes.
        if wait:
            while ('FAILED' not in status and
                   status != DELETED_STATE):
                self.sleep()

                try:
                    heat_stack = self.heat_c.stacks.get(
                        stack_id=name)
                except HTTPNotFound:
                    status = DELETED_STATE
                except HTTPException as e:
                    error_msg = ("Error retrieving [%s] stack information:"
                                 " %s" % (name, e))
                    raise ProviderException(error_msg)
                else:
                    status = heat_stack.stack_status

            if 'FAILED' in status:
                error_msg = "Failure deleting stack [%s]" % name
                raise ProviderException(error_msg)

        return {"status": status}
