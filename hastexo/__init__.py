from importlib import metadata
# __version__ attribute as suggested by (deferred) PEP 396:
# https://www.python.org/dev/peps/pep-0396/
#
# Single-source package definition as suggested (among several
# options) by:
# https://packaging.python.org/guides/single-sourcing-package-version/
__version__ = metadata.version('hastexo-xblock')
