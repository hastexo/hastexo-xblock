"""Setup for hastexo XBlock."""

import os
from setuptools import setup


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
    version='0.1.2',
    description='hastexo XBlock',
    packages=[
        'hastexo',
    ],
    install_requires=[
        'XBlock',
        'xblock-utils',
        'markdown2==2.3.0',
        'python-keystoneclient==2.0.0',
        'python-heatclient==0.8.0'
    ],
    entry_points={
        'xblock.v1': [
            'hastexo = hastexo:HastexoXBlock',
        ]
    },
    package_data=package_data("hastexo", ["static", "public"]),
)
