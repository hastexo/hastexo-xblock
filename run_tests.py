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
    # Find the location of the XBlock SDK. Note: it must be installed in development mode.
    # ('python setup.py develop' or 'pip install -e')
    xblock_sdk_dir = os.path.dirname(os.path.dirname(workbench.__file__))
    sys.path.append(xblock_sdk_dir)

    # Use the workbench settings file:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "workbench.settings")
    # Configure a range of ports in case the default port of 8081 is in use
    os.environ.setdefault("DJANGO_LIVE_TEST_SERVER_ADDRESS", "localhost:8081-8099")

    # Silence too verbose Django logging
    logging.disable(logging.DEBUG)

    try:
        os.mkdir('var')
    except OSError:
        # The var dir may already exist.
        pass

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
