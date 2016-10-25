"""Setup for hastexo XBlock."""

import os
from setuptools import setup

def package_scripts(root_list):
    data = []
    for root in root_list:
        for dirname, _, files in os.walk(root):
            for fname in files:
                data.append(os.path.join(dirname, fname))
    return data

def package_data(pkg, roots):
    """Generic function to find package_data.

    All of the files under each of the `roots` will be declared as package
    data for package `pkg`.

    """
    data = []
    for root in roots:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}

setup(
    name='hastexo-xblock',
    version='0.2.4',
    description='hastexo XBlock',
    packages=[
        'hastexo',
    ],
    install_requires=[
        'XBlock',
        'xblock-utils',
        'markdown2==2.3.0',
        'keystoneauth1==2.14.0',
        'python-keystoneclient==2.0.0',
        'python-heatclient==0.8.0',
        'python-swiftclient==3.1.0',
        'paramiko==2.0.2',
    ],
    entry_points={
        'xblock.v1': [
            'hastexo = hastexo:HastexoXBlock',
        ]
    },
    scripts=package_scripts(["bin"]),
    package_data=package_data("hastexo", ["static", "public"]),
)
