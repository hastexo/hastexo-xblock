#!/usr/bin/env python
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
    version='0.4.3',
    description='hastexo XBlock: Makes arbitrarily complex lab environments available on an Open edX LMS',
    url='https://github.com/hastexo/hastexo-xblock',
    author='hastexo',
    author_email='pypi@hastexo.com',
    license='AGPL-3.0',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: OpenStack',
        'Framework :: Django',
        'Intended Audience :: Education',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: POSIX :: Linux',
        'Topic :: Education :: Computer Aided Instruction (CAI)',
        'Topic :: Education',
    ],
    packages=[
        'hastexo',
    ],
    install_requires=[
        'XBlock',
        'xblock-utils',
        'keystoneauth1==2.14.0',
        'python-keystoneclient==2.0.0',
        'python-heatclient==0.8.0',
        'python-swiftclient==3.1.0',
        'oslo.utils==3.16.0',
        'oslo.config==3.17.0',
        'oslo.i18n==3.9.0',
        'oslo.serialization==2.13.0',
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
