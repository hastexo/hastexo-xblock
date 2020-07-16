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
    use_scm_version=True,
    description='hastexo XBlock: '
                'Makes arbitrarily complex lab environments '
                'available on an Open edX LMS',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
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
        'apscheduler',
        'google-api-python-client',
        'paramiko',
        'python-heatclient',
        'python-keystoneclient',
        'python-novaclient',
        'tenacity',
    ],
    entry_points={
        'xblock.v1': [
            'hastexo = hastexo.hastexo:HastexoXBlock',
        ]
    },
    scripts=package_scripts(["bin"]),
    package_data=package_data("hastexo",
                              ["static",
                               "public",
                               "management",
                               "migrations"]),
    setup_requires=['setuptools-scm'],
)
