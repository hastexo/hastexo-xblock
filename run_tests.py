#!/usr/bin/env python
"""
Run tests for the hastexo XBlock.

This script is required because the workbench SDK's settings file is not in any
python module.
"""

import logging
import os
import sys
import workbench
from coverage import coverage


if __name__ == "__main__":
    # Find the location of the XBlock SDK.
    # Note: it must be installed in development mode.
    # ('python setup.py develop' or 'pip install -e')
    xblock_sdk_dir = os.path.dirname(os.path.dirname(workbench.__file__))
    sys.path.append(xblock_sdk_dir)

    # Use the workbench settings file:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE",
                          "workbench.settings")
    # Configure a range of ports in case the default port of 8081 is in use
    os.environ.setdefault("DJANGO_LIVE_TEST_SERVER_ADDRESS",
                          "localhost:8081-8099")

    logging.basicConfig()

    try:
        os.mkdir('var')
    except OSError:
        # The var dir may already exist.
        pass

    # Add fake package to path.  Useful for duplicating modules the tests need
    # to import, but we don't want to install and can't easily mock (such as
    # `student.models.AnonymousUserId` from edx-platform).
    fake_package = os.path.join(os.path.dirname(__file__), 'fake')
    sys.path.insert(0, fake_package)

    from django.conf import settings
    settings.DEBUG = True
    settings.INSTALLED_APPS += ("hastexo", "student", )

    from django.core.management import execute_from_command_line
    args = sys.argv[1:]
    paths = [arg for arg in args if arg[0] != '-']
    if not paths:
        paths = ["tests/"]
    options = [arg for arg in args if arg not in paths]

    c = coverage(source=['hastexo'],
                 omit=['*tests*', '*heat-templates*',
                       '*src*', '*requirements'],
                 auto_data=True)
    c.start()
    execute_from_command_line([sys.argv[0], "test"] + paths + options)
    c.stop()
    c.report(show_missing=True)
