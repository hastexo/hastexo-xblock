from google.oauth2 import service_account
from googleapiclient.discovery import build


class GcloudService(object):
    """
    A meta-class for wrapping Gcloud services.

    """
    gc_info = (
        "type",
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "client_id",
        "auth_uri",
        "token_uri",
        "auth_provider_x509_cert_url",
        "client_x509_cert_url"
    )

    service_name = None
    api_version = None
    default_api_version = None
    info = {}

    def __init__(self, **info):
        self.api_version = info.get('gc_%s_api_version' % self.service_name)
        if not self.api_version:
            self.api_version = self.default_api_version

        for item in self.gc_info:
            self.info[item] = info.get('gc_%s' % item)

    def get_credentials(self):
        return service_account.Credentials.\
            from_service_account_info(self.info)

    def get_service(self):
        credentials = self.get_credentials()
        return build(self.service_name,
                     self.api_version,
                     credentials=credentials)


class GcloudDeploymentManager(GcloudService):
    """
    A class that wraps the Deployment Manager service for the Hastexo XBlock.

    """
    service_name = "deploymentmanager"
    default_api_version = "v2"


class GcloudComputeEngine(GcloudService):
    """
    A class that wraps the Compute Engine service for the Hastexo XBlock.

    """
    service_name = "compute"
    default_api_version = "v1"
