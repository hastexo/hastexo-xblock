Unreleased
---------------------------

* [Bug fix] Always display lab progress check hints as human readable strings
* [Testing] Fix Python 3.5 tests
* [Testing] Drop XBlock 1.1 from the test matrix

Version 3.6.3 (2020-05-20)
---------------------------

This is the last release to be tested against Python 2.7.
Any subsequent releases will support Python 3 only.

* [Enhancement] Support XBlock 1.3 (Python 3 only)
* [Enhancement] Refactor database error retries, using tenacity
* [Documentation] Update README

Version 3.6.2 (2020-05-05)
---------------------------

* [Bug fix] Retry database query to fetch per-provider stack count
* [Documentation] Add documentation for maintainers (on how to cut a
  release)
* [Documentation] Include README.md in the package’s PyPI description


Version 3.6.1 (2020-04-15)
---------------------------

* [Bug fix] Always, rather than selectively, retry failed database
  updates from Celery tasks

Version 3.6.0 (2020-03-30)
---------------------------

* [Enhancement] Allow nested blocks

Version 3.5.1 (2020-03-25)
---------------------------

* [Bug fix] Include suspended stacks in count to assess provider
  capacity and utilization

Version 3.5.0 (2020-03-19)
---------------------------

* [Enhancement] Retry failed database updates from Celery tasks

Version 3.4.2 (2020-01-23)
---------------------------

* [Security fix] test: Require django>=1.11.27 (CVE-2019-19844)
* [Enhancement] Bump XBlock 1.2 version to 1.2.9
* [Enhancement] Add Python 3.8 to test matrix

Version 3.4.1 (2020-01-07)
---------------------------

* [Bug fix] Use empty JSONFields instead of "null"
* [Enhancement] Refactor stack state variables
* [Bug fix] Add missing valid state, LAUNCH_TIMEOUT
* [Enhancement] Show coverage report at test end
* [Bug fix] Fix error handling when waiting for state change

Version 3.4.0 (2019-12-17)
---------------------------

* [Enhancement] Create admin page for stacks
* [Bug fix] Avoid unhandled exception on SSH close

Version 3.3.0 (2019-10-15)
---------------------------

* [Enhancement] Relax dependency constraints

Version 3.2.1 (2019-08-14)
---------------------------

* [Bug fix] Fix JSONField model and migration
* [Bug fix] Handle null `hook_events` properly

Version 3.2.0 (2019-08-13)
---------------------------

* [Enhancement] tox: Bump xblock12 env to XBlock 1.2.3
* [Enhancement] Add Python 3.7 to Travis configuration
* [Enhancement] tasks.py: continue on specific EnvironmentErrors during SSH connection
* [Enhancement] Update devstack documentation
* [Enhancement] Task hooks
* [DEPRECATION] `reboot_on_resume` will be removed in a future release, as its
  intended purpose is now better served by task hooks.
* [CONFIGURATION] The `suspend_in_parallel` configuration option is now a NOOP,
  as suspension now always happens in parallel via simultaneously running
  Celery tasks.

Version 3.1.1 (2019-08-02)
---------------------------

* [Bug fix] Fix XML parsing backward compatibility

Version 3.1.0 (2019-07-26)
---------------------------

* [BACKWARD INCOMPATIBLE FOR GCP LABS ONLY] Encode GCP stack names
* [Enhancement] Provider stack listing
* [Enhancement] Reaper zombie destroyer
* [Enhancement] Add Python 3.7 test target

Version 3.0.1 (2019-07-23)
---------------------------

* [Bug fix] Fix database logging
* [Enhancement] Improve suspender and reaper database logging

Version 3.0.0 (2019-07-18)
---------------------------

* [Enhancement] Refactor OpenStack client wrappers
* [Enhancement] Multi-cloud support
* [Enhancement] Introduce Gcloud provider driver
* [Bug fix] Fix Python 2-isms
* [Enhancement] Configurable guacd settings
* [Enhancement] Add docker support for guacamole app
* [Enhancement] Bump keystoneauth1
* [Bug fix] Fix app label
* [Enhancement] Bump os-client-config
* [Bug fix] Àdd missing init parameters to OpenStack wrappers
* [Enhancement] Avoid known stack suspension failure states

Version 2.6.0 (2019-03-06)
---------------------------

* [Enhancement] Progress check hints via stderr
* [Enhancement] Track XBlock-SDK master branch in test matrix
* [Bug fix] Python 3.6 compatibility
* [Enhancement] Managed package versions

Version 2.5.6 (2019-02-07)
---------------------------

* [Enhancement] Improve learner-facing warning messages

Version 2.5.5 (2019-01-30)
---------------------------

* [Enhancement] Continue SSH verification on EOFError
* [Enhancement] Also handle keystone HTTP exceptions
* [Bug fix] Fail if environment not found or template not provided

Version 2.5.4 (2018-12-17)
---------------------------

* [Bug fix] Handle all exceptions when suspending or reaping
* [Bug fix] Don't suspend or reap stacks with no provider
* [Bug fix] Don't delete manually resumed stacks
* [Bug fix] Refresh database connection on every run

Version 2.5.3 (2018-11-20)
---------------------------

* [Enhancement] Allow `launch_timeout` to be set per course
* [Enhancement] Allow CMS editing of ports, provider, tests
* [Enhancement] Wait for RDP connection
* [Enhancement] Deprecate custom XML parsing
* [Enhancement] Parse stack ports from XML
* [Enhancement] Handle all Heat HTTP exceptions

Version 2.5.2 (2018-11-09)
---------------------------

* [Enhancement] Don't create records implicitly
* [Bug fix] Wait for commit on LaunchStackTask()
* [Bug fix] Reset `error_msg` on stack launch
* [Bug fix] Only update necessary fields
* [Bug fix] Update provider in real time
* [Bug fix] Implement proper locking of `get_user_stack_status`
* [Bug fix] Roll back race condition check

Version 2.5.1 (2018-11-07)
---------------------------

* [Bug fix] Don't try to retrieve empty paths
* [Bug fix] Don't send reset request twice simultaneously
* [Bug fix] Avoid QuerySet cache
* [Bug fix] Avoid launch race condition
* [Bug fix] Don't update database from tasks.py
* [Bug fix] Stop browser timers on errors

Version 2.5.0 (2018-10-19)
---------------------------

* [Enhancement] Multiple provider support
* [Enhancement] Bump XBlock 1.2 testing to version 1.2.2
* [Security fix] Bump paramiko version

Version 2.4.1 (2018-10-14)
---------------------------

* [Enhancement] Update OpenStack client libraries

Version 2.4.0 (2018-08-21)
---------------------------

* [Enhancement] Hawthorn compatibility updates

Version 2.3.3 (2018-08-01)
---------------------------

* [Security fix] Address CVE-2018-7750

Version 2.3.2 (2018-06-14)
---------------------------

* [Enhancement] Handle general SSH exceptions gracefully
* [Enhancement] Use module constants for flags
* [Enhancement] Indirection and unit tests for `check_stack()`

Version 2.3.1 (2018-06-07)
---------------------------

* [Security fix] Tomcat8 CVE-2018-8014

Version 2.3.0 (2018-05-18)
---------------------------

* [Bug Fix] Fix the reaper's "MySQL has gone away" error
* [Enhancement] Rename 'Undertaker' to 'Reaper'
* [Enhancement] Use soft task timeouts

Version 2.2.0 (2018-04-24)
---------------------------

* [Enhancement] Implement stack deleter
* [Enhancement] Log stack model changes
* [Enhancement] Enforce task timeouts
* [Enhancement] Only log status changes
* [Enhancement] Retry stack deletion

Version 2.1.0 (2018-04-04)
---------------------------

* [Enhancement] Separate suspender program

Version 2.0.2 (2018-03-13)
---------------------------

* [Bug fix] Fuzz recurring poll timeouts
* [Bug fix] Don't send keepalives after guac error
* [Bug fix] Marginally improve the client's handling of Guacamole server errors

Version 2.0.1 (2018-03-02)
---------------------------

* [Security fix] Do not expose server-side configuration

Version 2.0.0 (2018-02-28)
---------------------------

* [Enhancement] Introduce reboot on resume
* [Bug fix] Disconnect immediately when idle
* [Enhancement] Fix unit tests
* [Bug fix] Fix typo in stack parameters invocation
* [Enhancement] Provide "run" parameter to stack templates
* [Enhancement] Multi-port support
* [Enhancement] Guacamole rewrite

Version 0.5.5 (2017-07-17)
---------------------------

* [Enhancement] Expand provider settings scope

Version 0.5.4 (2017-06-23)
---------------------------

* [Enhancement] Bump swift client to 3.3.0
* [Enhancement] Add XBlock 1.0.0 and Python 3.5 to the test matrix
* [Enhancement] Add mock to test requirements

Version 0.5.3 (2017-05-16)
---------------------------

* [Bug fix] Avoid another contextual version conflict

Version 0.5.2 (2017-05-12)
---------------------------

* [Bug fix] Freeze oslo requirements
* [Enhancement] PEP-8 compliance and flake8 testing
* [Enhancement] Enable automated testing via travis-ci

Version 0.5.1 (2017-05-02)
---------------------------

* [Enhancement] Tune requirements for latest edx-platform

Version 0.5.0 (2017-03-14)
---------------------------

* [Enhancement] Upgrade Heat wrapper

Version 0.4.3 (2017-01-17)
---------------------------

* [Bug fix] Freeze oslo
* [Enhancement] Add PyPI metadata

Version 0.4.2 (2016-12-02)
---------------------------

* [Bug fix] Fix ssh connection failure when a provider is set

Version 0.4.1 (2016-11-25)
---------------------------

* [Bug fix] Always download key during progress check
* [Bug fix] Fix check progress endless hang

Version 0.4.0 (2016-11-23)
---------------------------

* [Settings change] Multiple cloud providers
* [Breaks backward compatibility] Remove support for markdown instructions
* [Testing] Improve unit tests

Version 0.3.0 (2016-11-17)
---------------------------

* [UI change] Improve idle message
* [UI change] Implement reset button
* [UI change] Hide check progress button if there are no tests
* [Logging] Restructure log levels
