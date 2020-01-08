import time
import base64
import binascii
import hashlib
import paramiko
import random
import string
import yaml

try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO

from heatclient.exc import HTTPException, HTTPNotFound
from keystoneauth1.exceptions.http import HttpError
from novaclient.exceptions import ClientException
from googleapiclient.errors import Error as GcloudApiError
from googleapiclient.errors import HttpError as GcloudApiHttpError

from .common import (
    b,
    get_xblock_settings,
    IN_PROGRESS,
    FAILED,
    CREATE_COMPLETE,
    DELETE_COMPLETE,
    DELETE_IN_PROGRESS,
    RESUME_COMPLETE,
    RESUME_IN_PROGRESS,
    SUSPEND_COMPLETE,
    SUSPEND_IN_PROGRESS
)
from .openstack import HeatWrapper, NovaWrapper
from .gcloud import GcloudDeploymentManager, GcloudComputeEngine


class ProviderException(Exception):
    pass


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
        sleep_seconds = settings.get("sleep_timeout", 10)
        providers = settings.get("providers")
        config = providers.get(name)
        if config and isinstance(config, dict):
            provider_type = config.get("type")
            if provider_type == "openstack" or not provider_type:
                return OpenstackProvider(name, config, sleep_seconds)
            elif provider_type == "gcloud":
                return GcloudProvider(name, config, sleep_seconds)

    def __init__(self, name, config, sleep):
        self.name = name
        self.sleep_seconds = sleep

        # Get credentials
        if config and isinstance(config, dict):
            credentials = {}
            for key, default in self.default_credentials.items():
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

    def generate_key_pair(self, encodeb64=False):
        keypair = {}
        pkey = paramiko.RSAKey.generate(1024)
        keypair["public_key"] = pkey.get_base64()
        s = StringIO()
        pkey.write_private_key(s)
        k = s.getvalue()
        s.close()

        if encodeb64:
            k = base64.b64encode(b(k))

        keypair["private_key"] = k

        return keypair

    def generate_random_password(self, length):
        abc = string.ascii_lowercase
        return "".join(random.choice(abc) for i in range(length))

    def get_stacks(self):
        raise NotImplementedError()

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

    def get_stacks(self):
        stacks = []
        try:
            heat_stacks = self.heat_c.stacks.list()
        except HTTPNotFound:
            return stacks
        except (HTTPException, HttpError) as e:
            raise ProviderException(e)

        if heat_stacks:
            for heat_stack in heat_stacks:
                stack = {
                    "name": heat_stack.stack_name,
                    "status": heat_stack.stack_status
                }
                stacks.append(stack)

        return stacks

    def get_stack(self, name):
        try:
            heat_stack = self.heat_c.stacks.get(stack_id=name)
        except HTTPNotFound:
            status = DELETE_COMPLETE
            outputs = {}
        except (HTTPException, HttpError) as e:
            raise ProviderException(e)
        else:
            status = heat_stack.stack_status
            outputs = self._get_stack_outputs(heat_stack)

        return {"status": status,
                "outputs": outputs}

    def create_stack(self, name, run):
        if not self.template:
            raise ProviderException("Template not set for provider %s." %
                                    self.name)

        try:
            res = self.heat_c.stacks.create(
                stack_name=name,
                template=self.template,
                environment=self.environment,
                parameters={'run': run}
            )
        except (HTTPException, HttpError) as e:
            raise ProviderException(e)

        stack_id = res['stack']['id']

        # Sleep to avoid throttling.
        self.sleep()

        try:
            heat_stack = self.heat_c.stacks.get(stack_id=stack_id)
        except (HTTPException, HttpError) as e:
            raise ProviderException(e)

        status = heat_stack.stack_status

        # Wait for stack creation
        while IN_PROGRESS in status:
            self.sleep()

            try:
                heat_stack = self.heat_c.stacks.get(stack_id=heat_stack.id)
            except HTTPNotFound:
                raise ProviderException("Stack disappeared during creation.")
            except (HTTPException, HttpError) as e:
                raise ProviderException(e)

            status = heat_stack.stack_status

        if FAILED in status:
            raise ProviderException("Failure creating stack.")

        return {"status": status,
                "outputs": self._get_stack_outputs(heat_stack)}

    def resume_stack(self, name):
        try:
            self.heat_c.actions.resume(stack_id=name)
        except (HTTPException, HttpError) as e:
            raise ProviderException(e)

        status = RESUME_IN_PROGRESS

        # Wait until resume finishes.
        while (FAILED not in status and
               status != RESUME_COMPLETE):
            self.sleep()

            try:
                heat_stack = self.heat_c.stacks.get(
                    stack_id=name)
            except HTTPNotFound:
                raise ProviderException("Stack disappeared during resume.")
            except (HTTPException, HttpError) as e:
                raise ProviderException(e)
            else:
                status = heat_stack.stack_status

        if FAILED in status:
            raise ProviderException("Failure resuming stack")

        outputs = self._get_stack_outputs(heat_stack)

        # Reboot servers, if requested
        reboot_on_resume = outputs.get("reboot_on_resume")
        if (reboot_on_resume is not None and
                isinstance(reboot_on_resume, list)):
            for server in reboot_on_resume:
                try:
                    self.nova_c.servers.reboot(server, 'HARD')
                except ClientException as e:
                    raise ProviderException(e)

        return {"status": status,
                "outputs": outputs}

    def suspend_stack(self, name, wait=True):
        try:
            self.heat_c.actions.suspend(stack_id=name)
        except (HTTPException, HttpError) as e:
            raise ProviderException(e)

        status = SUSPEND_IN_PROGRESS

        # Wait until suspend finishes.
        if wait:
            while (FAILED not in status and
                   status != DELETE_COMPLETE and
                   status != SUSPEND_COMPLETE):
                self.sleep()

                try:
                    heat_stack = self.heat_c.stacks.get(
                        stack_id=name)
                except HTTPNotFound:
                    status = DELETE_COMPLETE
                except (HTTPException, HttpError) as e:
                    raise ProviderException(e)
                else:
                    status = heat_stack.stack_status

            if FAILED in status:
                raise ProviderException("Failure suspending stack.")

        return {"status": status}

    def delete_stack(self, name, wait=True):
        try:
            self.heat_c.stacks.delete(stack_id=name)
        except (HTTPException, HttpError) as e:
            raise ProviderException(e)

        status = DELETE_IN_PROGRESS

        # Wait until delete finishes.
        if wait:
            while (FAILED not in status and
                   status != DELETE_COMPLETE):
                self.sleep()

                try:
                    heat_stack = self.heat_c.stacks.get(
                        stack_id=name)
                except HTTPNotFound:
                    status = DELETE_COMPLETE
                except (HTTPException, HttpError) as e:
                    raise ProviderException(e)
                else:
                    status = heat_stack.stack_status

            if FAILED in status:
                raise ProviderException("Failure deleting stack.")

        return {"status": status}


class GcloudProvider(Provider):
    """
    Gcloud provider driver.

    """
    default_credentials = {
        "gc_deploymentmanager_api_version": "v2",
        "gc_compute_api_version": "v1",
        "gc_type": "service_account",
        "gc_project_id": "",
        "gc_private_key_id": "",
        "gc_private_key": "",
        "gc_client_email": "",
        "gc_client_id": "",
        "gc_auth_uri": "",
        "gc_token_uri": "",
        "gc_auth_provider_x509_cert_url": "",
        "gc_client_x509_cert_url": ""
    }
    ds = None
    cs = None
    project = None
    deployment_name_prefix = 's-'

    def __init__(self, provider, config, sleep):
        super(GcloudProvider, self).__init__(provider, config, sleep)

        self.ds = self._get_deployment_service()
        self.cs = self._get_compute_service()
        self.project = config.get("gc_project_id")

    def _get_deployment_service(self):
        return GcloudDeploymentManager(**self.credentials).get_service()

    def _get_compute_service(self):
        return GcloudComputeEngine(**self.credentials).get_service()

    def _get_deployment_outputs(self, deployment):
        name = deployment["name"]

        manifest_url = None
        if "update" in deployment and "manifest" in deployment["update"]:
            manifest_url = deployment["update"]["manifest"]
        elif "manifest" in deployment:
            manifest_url = deployment["manifest"]
        else:
            return {}

        manifest = manifest_url.split('/')[-1]
        try:
            response = self.ds.manifests().get(
                project=self.project,
                deployment=name,
                manifest=manifest
            ).execute()
        except GcloudApiError as e:
            raise ProviderException(e)

        outputs = {}
        if "layout" in response:
            try:
                layout = yaml.safe_load(response["layout"])
            except yaml.error.YAMLError:
                layout = None

            if not isinstance(layout, dict) or "outputs" not in layout:
                return {}

            for o in layout["outputs"]:
                if "finalValue" not in o or "name" not in o:
                    continue

                name = o["name"]
                value = o["finalValue"]

                # Decode private key, if in base64
                if name == "private_key":
                    try:
                        value = base64.decodestring(value).decode("utf-8")
                    except binascii.Error:
                        pass

                outputs[name] = value

        return outputs

    def _get_deployment_servers(self, deployment_name):
        try:
            response = self.ds.resources().list(
                project=self.project,
                deployment=deployment_name,
                filter='type = "compute.v1.instance"'
            ).execute()
        except GcloudApiError as e:
            raise ProviderException(e)

        servers = []
        if "resources" in response:
            for s in response["resources"]:
                try:
                    server_name = s["name"]
                    p = yaml.safe_load(s["finalProperties"])
                    server_zone = p["zone"]
                    server = self.cs.instances().get(
                        project=self.project,
                        zone=server_zone,
                        instance=server_name
                    ).execute()
                except (KeyError, yaml.error.YAMLError, GcloudApiError) as e:
                    raise ProviderException(e)

                servers.append(server)

        return servers

    def _get_deployment_status(self, deployment):
        deployment_name = deployment["name"]

        if "operation" not in deployment:
            raise ProviderException("Operation not found.")

        # Calculate operation status
        operation = deployment.get("operation")
        optype = operation["operationType"]
        if optype == "insert":
            optype = "CREATE"
        elif optype == "update":
            optype = "UPDATE"
        elif optype == "delete":
            optype = "DELETE"
        else:
            raise ProviderException("Unknown operation type %s" % optype)

        opstatus = operation["status"]
        if opstatus == "DONE":
            opstatus = "COMPLETE"
        elif opstatus == "PENDING" or opstatus == "RUNNING":
            opstatus = IN_PROGRESS
        else:
            raise ProviderException("Unknown operation status %s" % opstatus)

        status = "%s_%s" % (optype, opstatus)

        # Calculate suspend status
        if status == CREATE_COMPLETE:
            servers = self._get_deployment_servers(deployment_name)
            if servers:
                if any(s.get("status") == "STOPPING" for s in servers):
                    status = SUSPEND_IN_PROGRESS
                elif any(s.get("status") == "STAGING" for s in servers):
                    status = RESUME_IN_PROGRESS
                elif all(s.get("status") == "TERMINATED" for s in servers):
                    status = SUSPEND_COMPLETE

        return status

    def _encode_name(self, name):
        """
        GCP enforces strict resource naming policies (regex
        '[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?'), so we work around it by naming
        the stack with a hash.

        """
        digest = hashlib.sha1(b(name)).hexdigest()
        return '%s%s' % (self.deployment_name_prefix, digest)

    def get_stacks(self):
        stacks = []

        try:
            response = self.ds.deployments().list(
                project=self.project
            ).execute()
        except GcloudApiHttpError as e:
            if e.resp.status == 404:
                return stacks
            else:
                raise ProviderException(e)
        except GcloudApiError as e:
            raise ProviderException(e)

        for deployment in response.get("deployments", []):
            if not deployment["name"].startswith(self.deployment_name_prefix):
                continue

            try:
                stack = {
                    "name": deployment["description"],
                    "status": self._get_deployment_status(deployment)
                }
            except Exception:
                continue

            stacks.append(stack)

        return stacks

    def get_stack(self, name):
        deployment_name = self._encode_name(name)

        try:
            response = self.ds.deployments().get(
                project=self.project, deployment=deployment_name
            ).execute()
        except GcloudApiHttpError as e:
            if e.resp.status == 404:
                status = DELETE_COMPLETE
                outputs = {}
            else:
                raise ProviderException(e)
        except GcloudApiError as e:
            raise ProviderException(e)
        else:
            status = self._get_deployment_status(response)
            outputs = self._get_deployment_outputs(response)

        return {"status": status,
                "outputs": outputs}

    def create_stack(self, name, run):
        deployment_name = self._encode_name(name)

        properties = {"run": run}

        # Generate key pair with a b64-encoded private key because Deployment
        # Manager can't handle properties with multi-line values
        properties.update(self.generate_key_pair(True))

        # Generate random password
        properties["password"] = self.generate_random_password(64)

        # Update properties with user-defined values
        try:
            env = yaml.safe_load(self.environment)
        except (AttributeError, yaml.error.YAMLError):
            raise ProviderException("Invalid environment YAML.")

        if not isinstance(env, dict) or "properties" not in env:
            raise ProviderException("Invalid environment YAML.")

        properties.update(env.get("properties", {}))

        # Create template resource
        template_path = "%s.yaml.jinja" % deployment_name
        resource = {
            "name": deployment_name,
            "type": template_path,
            "properties": properties
        }

        # Build outputs
        outputs = [
            {"name": "public_ip",
             "value": "$(ref.%s.public_ip)" % deployment_name},
            {"name": "private_key",
             "value": properties["private_key"]},
            {"name": "password",
             "value": properties["password"]}
        ]

        # Build config
        config = {
            "imports": [{"path": template_path}],
            "resources": [resource],
            "outputs": outputs
        }

        # Build request body
        body = {
            "target": {
                "imports": [{
                    "name": template_path,
                    "content": self.template
                }],
                "config": {
                    "content": yaml.safe_dump(config, default_flow_style=False)
                }
            },
            "name": deployment_name,
            "description": name
        }

        try:
            operation = self.ds.deployments().insert(
                project=self.project, body=body
            ).execute()

            # Wait for operation to complete
            while True:
                response = self.ds.operations().get(
                    project=self.project,
                    operation=operation["name"]
                ).execute()

                if response["status"] == "DONE":
                    if "error" in response:
                        errors = response["error"].get("errors")
                        if errors:
                            message = errors[0]["message"]
                        else:
                            message = "Error in operation."
                        raise ProviderException(message)
                    break

                self.sleep()
        except GcloudApiError as e:
            raise ProviderException(e)

        return self.get_stack(name)

    def delete_stack(self, name, wait=True):
        deployment_name = self._encode_name(name)

        try:
            operation = self.ds.deployments().delete(
                project=self.project, deployment=deployment_name
            ).execute()
        except GcloudApiError as e:
            raise ProviderException(e)

        status = DELETE_IN_PROGRESS

        # Wait until delete finishes.
        if wait:
            while True:
                try:
                    response = self.ds.operations().get(
                        project=self.project,
                        operation=operation["name"]
                    ).execute()

                    if response["status"] == "DONE":
                        if "error" in response:
                            errors = response["error"].get("errors")
                            if errors:
                                message = errors[0]["message"]
                            else:
                                message = "Error in operation."
                            raise ProviderException(message)

                        status = DELETE_COMPLETE
                        break
                except GcloudApiHttpError as e:
                    if e.resp.status == 404:
                        status = DELETE_COMPLETE
                        break
                    else:
                        raise ProviderException(e)
                except GcloudApiError as e:
                    raise ProviderException(e)

                self.sleep()

        return {"status": status}

    def suspend_stack(self, name, wait=True):
        deployment_name = self._encode_name(name)

        # Get servers
        servers = self._get_deployment_servers(deployment_name)

        for server in servers:
            status = server.get("status")
            if status == "RUNNING":
                try:
                    self.cs.instances().stop(
                        project=self.project,
                        zone=server["zone"].split('/')[-1],
                        instance=server["name"]
                    ).execute()
                except GcloudApiError as e:
                    raise ProviderException(e)
            elif (status != "STOPPING" and
                  status != "TERMINATED"):
                raise ProviderException("Cannot not stop server %s with status"
                                        " %s" % (server["name"],
                                                 server["status"]))

        status = SUSPEND_IN_PROGRESS

        # Wait until suspend finishes.
        if wait:
            while True:
                self.sleep()
                servers = self._get_deployment_servers(deployment_name)
                if all(s.get("status") == "TERMINATED" for s in servers):
                    status = SUSPEND_COMPLETE
                    break

        return {"status": status}

    def resume_stack(self, name):
        deployment_name = self._encode_name(name)

        # Start the servers
        servers = self._get_deployment_servers(deployment_name)
        for server in servers:
            status = server.get("status")
            if status == "TERMINATED":
                try:
                    self.cs.instances().start(
                        project=self.project,
                        zone=server["zone"].split('/')[-1],
                        instance=server["name"]
                    ).execute()
                except GcloudApiError as e:
                    raise ProviderException(e)
            elif (status != "RUNNING" and
                  status != "STAGING"):
                raise ProviderException("Cannot not stop server %s with status"
                                        " %s" % (server["name"],
                                                 server["status"]))

        # Wait until resume finishes.
        while True:
            servers = self._get_deployment_servers(deployment_name)
            if all(s.get("status") == "RUNNING" for s in servers):
                break

            self.sleep()

        return self.get_stack(name)
