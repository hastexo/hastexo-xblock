# -*- coding: utf-8 -*-
"""
Swift utility classes.

"""
import os

from swiftclient.service import SwiftService, SwiftUploadObject
from swiftclient.exceptions import ClientException


class SwiftWrapper(object):
    """
    A class that wraps the Swift service for the Hastexo XBlock.

    """
    os_options = (
        'os_auth_url',
        'os_auth_token',
        'os_username',
        'os_password',
        'os_user_id',
        'os_user_domain_id',
        'os_user_domain_name',
        'os_tenant_id',
        'os_tenant_name',
        'os_project_id',
        'os_project_name',
        'os_project_domain_id',
        'os_project_domain_name',
        'os_service_type',
        'os_endpoint_type',
        'os_storage_url',
        'os_region_name'
    )

    options = {}

    ssh_bucket = ""

    def __init__(self, **configuration):
        self.ssh_bucket = configuration.get("ssh_bucket", "identities")

        # Set OpenStack options
        credentials = configuration.get("credentials")
        for os_option in self.os_options:
            self.options[os_option] = credentials.get(os_option)

    def upload_key(self, key, key_path):
        # Upload it
        error = None
        with SwiftService(options=self.options) as swift:
            obj = SwiftUploadObject(key_path, object_name=key)
            for r in swift.upload(self.ssh_bucket, [obj]):
                if not r['success']:
                    error = r['error']
                    container = r['container']
                    if 'action' in r and r['action'] == "create_container":
                        # Failure to create container is not a problem
                        continue
                    if isinstance(error, ClientException) and error.http_status == 413:
                        print("File too large '{0}/{1}'".format(container, key))
                        continue

    def download_key(self, key, key_path):
        options = self.options
        options["out_file"] = key_path
        options["skip_identical"] = True

        # Download it
        error = None
        with SwiftService(options=options) as swift:
            for r in swift.download(self.ssh_bucket, [key]):
                if not r['success']:
                    error = r['error']
                    container = r['container']
                    obj = r['object']
                    if isinstance(error, ClientException):
                        # Skipped identical is not an error
                        if error.http_status == 304 and options["skip_identical"]:
                            continue
                        # Ignore missing object: upload is optional
                        if error.http_status == 404:
                            print("Object '{0}/{1}' not found".format(container, obj))
                            continue
                        print("Could not download '{0}/{1}'".format(container, obj))

        # Fix permissions so SSH doesn't complain
        if not error:
            os.chmod(key_path, 0600)
