Version 8.1.0 (2024-11-20)
-------------------------
* [Chore] Update requirements.

Version 8.0.1 (2024-11-13)
-------------------------
* [Bug fix] Add more authentication checks when accessing a fullscreen
  lab directly from an URL. Return a 401 when user is not authenticated
  on the platform.

Version 8.0.0 (2024-10-16)
-------------------------
* Drop support for Python 3.8 and `XBlock<2` (and, as a consequence,
  any Open edX releases prior to Redwood).

Version 7.13.0 (2024-09-27)
-------------------------
* [Enhancement] Enable `show_in_read_only_mode` XBlock attribute
  to allow instuctors to use this XBlock while masquerading
  as a specific learner.

Version 7.12.0 (2024-08-06)
-------------------------
* [Enhancement] Add support for the Open edX Redwood release.

Version 7.11.0 (2024-05-06)
-------------------------
* [Enhancement] Update to a newer Twisted version.
* [Enhancement] Update to a newer Paramiko version.

Version 7.10.1 (2024-04-23)
-------------------------
* [Bug fix] Stop installing the XBlock in editable mode with `-e .`

Version 7.10.0 (2024-04-15)
-------------------------
* [Enhancement] Add better error handling for missing Provider configuration.
* [Enhancement] Add support for Python 3.12.

Version 7.9.1 (2024-02-14)
-------------------------
* [Bug fix] Don't allow accessing a fullscreen lab directly from a URL,
  when the user is unauthenticated. Return a 401 right away when attempted.

Version 7.9.0 (2024-01-11)
-------------------------
* [Enhancement] Add support for Apache Guacamole 1.5.4;
  make it the new default version.
* [Enhancement] Update requirements for Open edX Quince release.

Version 7.8.1 (2023-12-18)
-------------------------
* [Bug fix] Include missing XBlock attributes in a course export.
* [Bug fix] Fix `enable_fullscreen` setting overrides via the XBlock
  attribute.

Version 7.8.0 (2023-12-13)
-------------------------
* [Enhancement] Add an option to launch the lab in a new window.

Version 7.7.3 (2023-12-04)
-------------------------
* [Bug fix] Fix private key getting lost after a stack resume failure.
  Make sure we keep the stack key in place when running cleanup on
  a stack that failed to resume.

Version 7.7.2 (2023-09-15)
-------------------------
* [Bug fix] Fix editing the `stack_key_type` field in Studio; include
  the attribute in Studio export.
* [Bug fix] Add better handling for SSH key cleanup when deleting stacks.

Version 7.7.1 (2023-09-13)
-------------------------
* [Bug fix] Fix resuming a lab stack when the `stack_key_type`
  attribute is used and the SSH key for the lab is generated
  by the XBlock.
* [Bug fix] Restrict Twisted dependency to `twisted<23.8.0` to remain
  installable on Python 3.8 and 3.9.

Version 7.7.0 (2023-08-24)
-------------------------
* [Enhancement] Add support for Ed25519 SSH keys by introducing
  a new optional XBlock attribute `stack_key_type`. When used, it
  is possible to generate either `RSA` or `Ed25519` key for the lab.
  If set to `None`(default), the key handling should be done via the
  lab template, as it has been so far.

Version 7.6.0 (2023-06-26)
-------------------------
* [Enhancement] Add support for Apache Guacamole 1.5.2;
  make it the new default version.

Version 7.5.0 (2023-03-14)
-------------------------
* [Enhancement] Update requirements for Open edX Olive release.

Version 7.4.0 (2023-02-20)
-------------------------
* [Bug fix] Restore the `paste` functionality by addressing
  the related changes in the `guacamole-js` library.
* [Enhancement] Add support for copying text out from
  the terminal using the Async Clipboard API.
  This works on Mozilla Firefox at this time. Support
  in other browsers may follow.

Version 7.3.0 (2023-01-20)
-------------------------
* [Enhancement] Add internationalization support.

Version 7.2.0 (2022-11-17)
-------------------------
* [Enhancement] Add learner email to stacklist view in the
  admin page and include it in searchable fields.

Version 7.1.0 (2022-11-07)
-------------------------
* [Enhancement] Add custom actions to the admin interface to
  - clear the stacklog for selected stack(s),
  - set status to `SUSPEND_COMPLETE` for selected stack(s).
  
  Clearing the stacklog will be particulary useful in cases
  we need to "reset" a lab usage timer, since the
  time is accumulated by the stacklog entries.
  Setting a status to `SUSPEND_COMPLETE` is a common fix for
  stacks that end up in unexpected states.

Version 7.0.1 (2022-10-04)
----------
* [Bug fix] Retry `read_from_contentstore()`. Use `tenacity`'s
  retry functionality for getting course information from contentstore.

Version 7.0.0 (2022-08-22)
-------------------------
* [Bug fix] From Celery 5.0.0 the legacy task API was discontinued.
  This meant that the Task base class no longer automatically registered 
  child tasks in Open edX Nutmeg (which uses Celery 5.2.6). 
  Manually register the class-based tasks on the Celery app instance.
* [BREAKING CHANGE] Update the `hastexo_guacamole_client` to
  Channels 3. The asgi root application (`ASGI_APPLICATION`)
  is now defined in the `asgi.py` file instead of `routing.py` file.
  The asgi application now also checks for allowed hosts,
  meaning if you want to allow the LMS to connect to labs via the `hastexo_guacamole_client`, the LMS host has to be listed in
  `ALLOWED_HOSTS` at `hastexo_guacamole_client.settings.py`.
* [Documentation] Remove obsolete deployment instructions for the
  old “native” (Ansible-based) installation, and the old Devstack.

Version 6.2.0 (2022-07-21)
-------------------------

* [Enhancement] Add an option to override the `suspend_timeout`
  global setting via an XBlock attribute, in seconds.

Version 6.1.5 (2022-07-13)
-------------------------

* [Bug fix] Fix migrations around the `lab_usage_limit` feature
  introduced in 6.1.0. This unbreaks migrations in the event that some
  stacks cannot be linked to an existing user account.

Version 6.1.4 (2022-07-06)
-------------------------

* [Bug fix] Bring back `asgiref` constraint and lower
  `Django` constraint. These need to be
  in sync with the `channels` version requirements.

Version 6.1.3 (2022-06-29)
-------------------------

* [Bug fix] Add a check to the `add_user_foreign_key` migration
  file to find stacks that are missing a link to a real user account.
  If such stack(s) exist, do not attempt to apply the migration,
  instead raise an exception and provide an error message with
  guidance on how to proceed.

Version 6.1.2 (2022-06-22)
-------------------------

* [Enhancement] Install a newer version of the Paramiko library.
* [Bug fix] Set upper bounds for the `install_requires` list in
  `setup.py`, to match those set in `requirements.txt`. This fixes a
  version incompatibility problem when the package is installed by pip
  version 20 and earlier, which would lead to
  `pkg_resources.ContextualVersionConflict` errors when deployed on
  Open edX Maple.
* [Testing] Enhance the test matrix to include the pip versions used
  in Open edX Maple (20.0.2) and Nutmeg (22.0.4), and use pipdeptree
  to automatically flag dependency version inconsistencies.

Version 6.1.1 (2022-04-25)
-------------------------
* [Enhancement] Add `hidden` option for spinning up a lab
  environment in the background while the lab itself is hidden.

Version 6.1.0 (2022-04-21)
-------------------------
* [Enhancement] Be more specific when raising the exception for
  restricting lab access due to lab usage limit being reached.
* [Enhancement] Add an option to track and limit a learners lab
  usage. To support time tracking, link a learner to their stacks
  across the platform by adding a Foreign Key field for user to
  the Stack object.
  Add configuration options for setting a time limit for using labs
  (`lab_usage_limit`) in seconds and how to handle a breach of the
  set limit (`lab_usage_limit_breach_policy`).
* [Testing] Include XBlock 1.6 in the test matrix.

Version 6.0.1 (2022-03-14)
-------------------------
* [Documentation] Update README with improved instructions for Open
  edX Maple (using Tutor) and Lilac (using edx-configuration).

Version 6.0.0rc0 (2022-02-23)
-------------------------
* [Bug fix] Don't fail to run if a listed provider is not
  configured. Allow to move on to the next provider and log a
  warning message for the provider initialisation failure.
* [BREAKING CHANGE] Update the `GUACD_*` environment variables to
  better suit a Tutor deployment. Rename the variables to
  `GUACD_SERVICE_HOST` and `GUACD_SERVICE_PORT` to directly read
  values set for the guacd service with the `tutor k8s` deployment.
  Update the default values to support the `tutor local`/
  `tutor dev` deployment.
* [BREAKING CHANGE] Update dependencies that should be in sync with
  `edx-platform` to support the `Maple` release.
  As of 6.0, this XBlock only supports Open edX versions Maple and
  higher. As the community has switched the supported deployment method
  from edx-configuration playbooks to Tutor, this XBlock can also
  be deployed with Tutor only. Instructions for the latter can be found
  in the README.
* [Enhancement] Add support for Tutor deployment, by dropping the
  `wait_for_ping` logic.
* [Enhancement] Add support for Apache Guacamole version `1.4.0`,
  make it the new default.
* [Enhancement] Make the `guacamole-common-js` library version
  configurable by the `guacamole_js_version` setting.
* [Bug fix] Fix unbalanced tags (`<p>` vs. `<div>`) in the static
  `main.html` template.
* [Testing] Add basic HTML validation for static templates.

Version 5.0.17 (2022-01-04)
-------------------------
* [Enhancement] Add constraints to Django version requirement for
  the `hastexo_guacamole_client`.

Version 5.0.16 (2021-09-01)
-------------------------
* [Bug fix] Make sure that any error message that is added to the
  `error_msg` field of a stack, gets truncated before a stack update.
* [Testing] Include XBlock 1.5 in the test matrix, remove XBlock 1.3.
* [Testing] Include Python 3.9 in the test matrix, remove remnants of
  Python 3.5 test coverage.

Version 5.0.15 (2021-06-11)
-------------------------
* [Bug fix] Truncate the error message for `LaunchError` to fit
  256 characters and thus, could be added to the `error_msg` field
  of a `Stack`.

Version 5.0.14 (2021-06-02)
-------------------------
* [Bug fix] Make XBlock exports (from Studio or its REST API)
  deterministic and predictable.
* [Enhancement] Add tests for the new export/import logic.
* [Bug fix] Restrict stack names to ASCII characters and digits.

Version 5.0.13 (2021-05-21)
-------------------------
* [Bug fix] Fix RDP connectivity check for IPv6 stacks.

Version 5.0.12 (2021-05-12)
-------------------------
* [Enhancement] Speed up progress checks by reducing the sleep time when
  waiting for a remote execution of a command to finish.

Version 5.0.11 (2021-05-10)
-------------------------
* [Bug fix] Add constraints to `dogpile.cache` and `cliff`, so that our
  OpenStack client libraries will not have dependency conflicts.

Version 5.0.10 (2021-04-26)
-------------------------
* [Enhancement] Relax version constraints in `requirements/base.txt`
  so that the OpenStack Train release becomes our reference point for
  OpenStack client libraries. Simultaneously, relax the version
  constraints for Paramiko and Tenacity.

Version 5.0.9 (2021-04-22)
-------------------------
* [Enhancement] Display the "check progress" button (if enabled) in
  blue, to provide greater contrast to the red reset button.
* [Enhancement] Make the warning learners see when they reset a lab
  more verbose. Also, add a specific warning in case the XBlock is
  being displayed in a timed exam, indicating that the exam timer will
  continue to run while the lab is being reset.

Version 5.0.8 (2021-04-21)
-------------------------
* [Bug fix] Revert previous unsuccessful attempt to refactor Celery
 logic.
* [Bug fix] Use the "old" Celery Task base class, which our tasks
  were originally built on.

Version 5.0.7 (2021-04-16)
-------------------------
**Do not use this release.** This contains a change breaking Celery
task invocation, and was never published on PyPI.

* [Bug fix] Refactor Celery tasks logic to define a Celery app
  and register our class based tasks to that app.

Version 5.0.6 (2021-04-07)
--------------------------
* [Bug fix] Refactor closing ssh connection in `finally` blocks.

Version 5.0.5 (2021-03-30)
--------------------------
* [Bug fix] Add `null=True` for `key` and `password` in the Stack
  model. The fix in 5.0.4 does not lead to the desired schema update
  on MariaDB 10.2 (it does not change the schema at all), so rather
  than using a default, allow NULL values instead.

Version 5.0.4 (2021-03-26)
--------------------------
* [Enhancement] Use full names for common.djangoapps imports from
  edx-platform.
* [Enhancement] Update requirements for Open EdX Koa release.
* [Bug fix] Fix two missing defaults in the Stack model.

Version 5.0.3 (2021-03-22)
---------------------------
* [Bug fix] Update test dependencies to address
  [CVE-2021-3281](https://nvd.nist.gov/vuln/detail/CVE-2021-3281).
* [Enhancement] Add logging to provider actions, to make interactions
  with cloud platforms more easily traceable.

Version 5.0.2 (2021-03-17)
---------------------------
* [Bug fix] Make Paramiko SSH connections more robust against socket
  timeouts (and retry the connection if it runs into one).

Version 5.0.1 (2021-03-04)
---------------------------
* [DEPRECATION] As of this release, the previous implementation that
  relied on the Guacamole Tomcat servlet is deprecated. A `stable-4.1`
  branch exists that might still receive bugfixes for some time, but
  do not count on this being supported any longer than the lifetime of
  the Open edX Koa release. The [Ansible
  playbooks](https://github.com/hastexo/edx-configuration/tree/hastexo/juniper/hastexo_xblock)
  that tie into `edx-configuration` have been updated to “do the right
  thing” based on the hastexo XBlock version being deployed: for
  version 5 and up, they deploy Daphne and pyguacamole; for earlier
  versions, they continue to deploy Tomcat and the Guacamole servlet.

Version 5.0.0rc6 (2021-03-01)
---------------------------
* [Bug fix] Add a default `port` value for `rdp` connections.

Version 5.0.0rc5 (2021-02-23)
----------------------------

* Merge recent changes from 4.1 into 5.0 RC branch.

Version 5.0.0rc3 (2021-02-22)
----------------------------
* [Bug fix] Fix `read_only` mode `key` and `mouse` event filtering
  logic.

Version 5.0.0rc2 (2021-02-19)
-----------------------------
* [Enhancement] Implement the `read_only` mode in the websocket
  consumer by not passing any `key` or `mouse` events to `guacamole`
  when set to `True`.
* [Bug fix] Include `stack_protocol` attribute when initializing the
  javascript code so that the terminal height value will be calculated
  correctly.
* [Bug fix] Refactor asyncio task creation logic to also work with
  python3.5.
* [Bug fix] Add missing dependencies for `hastexo_guacamole_client`.

Version 5.0.0rc1 (2021-02-16)
-----------------------------
* [Enhancement] Allow overriding settings for the
  `hastexo_guacamole_client` from a configuration file by defining
  it as `HASTEXO_GUACAMOLE_CFG`.

Version 5.0.0rc0 (2021-02-02)
-----------------------------
* [BREAKING CHANGE] Replace Guacamole servlet with a Django ASGI
  application, which uses Django-Channels and the
  [pyguacamole](https://pypi.org/project/pyguacamole/) library.  
  As of 5.0, deployment of this XBlock will no longer rely on the
  Apache Tomcat servlet container, which Guacamole normally uses, but
  instead on the Daphne ASGI server. If you have been deploying this
  XBlock with the modified edx-configuration playbooks as explained in
  the README, deployment should still be automatic for you. It is,
  however, strongly advised that you respin your app servers from
  scratch, in order to keep any residual Tomcat servlet configuration
  from lingering on them.

Version 4.1.11 (2021-02-23)
-------------------------
* [Bug fix] When deleting learner state, the `stack_name` value
  gets wiped out. If we then try to update the stack (for example
  via `keepalive`) we get `Stack.DoesNotExist` error. Check if
  `stack_name` has a value before attempting to update and if not,
  set it again.

Version 4.1.10 (2021-02-11)
-------------------------
* [Bug fix] Implement more of `ScorableXBlockMixin` functionality
  for using the grading related instructor tasks like overriding
  and rescoring learner's submissions.

Version 4.1.9 (2021-02-10)
-------------------------
* [Bug fix] Make the XBlock a subclass of `ScorableXBlockMixin` so
  grades would be calculated correctly for each subsection.
* [Enhancement] Make progress check wait dialog wording more general
  and more suitable for different progress check configurations.

Version 4.1.8 (2021-02-02)
-------------------------
[Bug fix] Fix export error, when provider attributes are not defined.

Version 4.1.7 (2021-01-29)
-------------------------
[Enhancement] Make the progress check result header configurable
 and allow to enable/disable showing feedback for task completion.

Version 4.1.6 (2021-01-26)
-------------------------
[Enhancement] Allow to enable/disable displaying test stderr
  output streams as hints.
[Enhancement] Make the progress check button label configurable.

Version 4.1.5 (2021-01-25)
--------------------------
* [Bug fix] Fix ICMP connectivity check for IPv6-only stacks.

Version 4.1.4 (2021-01-14)
--------------------------
* [Enhancement] Run integration tests in GitHub Actions, rather than
  Travis CI.
* [Bug fix] Only add `template` and `environment` attributes
  to a provider during course export and import when they have a value.
  Adding a `null` or `None` values can cause breakage with spinning up labs.
* [Enhancement] Update test requirements.

Version 4.1.3 (2020-12-11)
---------------------------

* [Enhancement] Add a `read_only` XBlock attribute which, when set,
  blocks all keyboard and mouse interaction with the Guacamole
  terminal (effectively rendering it read-only). Defaults to `false`,
  meaning the terminal is rendered with full interactivity by default.

Version 4.1.2 (2020-12-03)
---------------------------

* [Bug fix] The XBlock allows to configure the layout for lab
  instructions to be either above, below, left or right from the
  terminal.  However, that configuration was not working properly for
  lab instructions that are in a nested block.

Version 4.1.1 (2020-11-23)
---------------------------

* [Bug fix] Correct the erroneous Maven `pom.xml` that accidentally
  bumped 4.0.0 references to 4.1.0 in the prior release. It should
  obviously have only bumped the package's own `<version>` string, and
  not the model version, schema, or namespace reference.

Version 4.1.0 (2020-11-23)
---------------------------

**Do not use this release.** An erroneous invocation of `bumpversion`
resulted in a Maven `pom.xml` that renders the Guacamole subsystem
`.war` file impossible to build.

* [Enhancement] Refactor course export/import logic. XBlock editable
  fields are added as attributes to the <hastexo> element in a
  vertical block.  `hook_events`, `ports`, `providers` and `tests` are
  exported to a separate xml file. This does not affect existing
  deployed courses using the XBlock, but might possibly require some
  tweaking to automated deployment pipelines that rely on import and
  export.
* [Bug fix] Fix support for nested `<video>` elements.
* [Enhancement] Support `<markdown>` (from the
  [markdown-xblock](https://pypi.org/project/markdown-xblock/)
  package) as an additional nested element (in addition to `<html>`,
  `<pdf>`, and `<video>`).

Version 4.0.0 (2020-11-10)
---------------------------

* [Enhancement] Enable overriding 'delete_age' via XBlock attribute in seconds.
  The global settings still only accepts 'delete_age' value in days but
  is now converted to seconds internally. In future releases the settings will
  begin to support suffixes 'd', 'h', 'm' and 's'.
* [BACKWARD INCOMPATIBLE] This release removes Python 2.7 from the
  test matrix. This in turn means that we have also removed XBlock 1.1
  and XBlock 1.2 from the test matrix (both of which rely on Python
  2).
* [Testing] Include XBlock 1.4 in the test matrix.
* [Testing] Include a .gitlab-ci.yml file for running CI tests
  when mirroring this repository onto a public or private GitLab
  instance.

Version 3.6.10 (2020-10-21)
---------------------------

* [UI change] Disable page auto-scroll when terminal gets focused

Version 3.6.9 (2020-08-13)
---------------------------

* [Bug fix] Minor style fixes for layout options

Version 3.6.8 (2020-08-11)
---------------------------

* [Enhancement] Make instructions layout configurable (experimental)

Version 3.6.7 (2020-08-03)
---------------------------

* [Bug fix] Terminal font size configuration value type fix

Version 3.6.6 (2020-08-03)
---------------------------

* [Enhancement] Make Guacamole terminal color scheme and font configurable

Version 3.6.5 (2020-07-16)
---------------------------

* [Bug fix] Correctly include the "reaper" and "suspender" manage.py
  commands in packaging.
* [Testing] Include unit tests for the manage.py commands.


Version 3.6.4 (2020-07-16)
---------------------------

* [Bug fix] Always display lab progress check hints as human readable strings
* [Testing] Drop XBlock 1.1 from the test matrix
* [Testing] Match up XBlock and Python version according to Open edX named releases
* [Testing] Fix Python 3.5 tests

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
