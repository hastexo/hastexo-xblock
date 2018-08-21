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
