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
    python_requires='>=3.11',
    install_requires=[
        'apscheduler<4',
        'cliff<=4.7',
        'dogpile.cache<=1.3',
        'google-api-python-client<=2.149.0',
        'keystoneauth1<=5.8',
        'openstacksdk<=4.1',
        'osc-lib<=3.1',
        'os-client-config<=2.1',
        'oslo.serialization<=5.5',
        'oslo.utils<=7.4',
        'oslo.config<=9.7.1',
        'paramiko>=3.4.0,<4',
        'python-heatclient<=4.0',
        'python-keystoneclient<=5.5',
        'python-novaclient<=18.7',
        'tenacity<=9.0',
    ],
    entry_points={
        'xblock.v1': [
            'hastexo = hastexo.hastexo:HastexoXBlock',
        ]
    },
    scripts=package_scripts(["bin"]),
    include_package_data=True,
    package_data=package_data("hastexo",
                              ["static",
                               "public",
                               "management",
                               "migrations",
                               "translations",
                               "locale"]),
    setup_requires=['setuptools-scm'],
)
