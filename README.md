[![PyPI version](https://img.shields.io/pypi/v/hastexo-xblock.svg)](https://pypi.python.org/pypi/hastexo-xblock)
[![Build Status](https://travis-ci.org/hastexo/hastexo-xblock.svg?branch=master)](https://travis-ci.org/hastexo/hastexo-xblock) [![codecov](https://codecov.io/gh/hastexo/hastexo-xblock/branch/master/graph/badge.svg)](https://codecov.io/gh/hastexo/hastexo-xblock)

# hastexo XBlock

The hastexo [XBlock](https://xblock.readthedocs.org/en/latest/) is an
[Open edX](https://open.edx.org/) API that integrates realistic lab
environments into distributed computing courses. The hastexo XBlock allows
students to access an OpenStack environment within an edX course.

It leverages [Apache Guacamole](https://guacamole.incubator.apache.org/) as a
browser-based connection mechanism, which includes the ability to connect to
graphical user environments (via VNC and RDP), in addition to terminals (via
SSH).

-> If you are looking for the legacy GateOne functionality, please check out
-> the documentation in
-> [the `stable-0.5` branch](https://github.com/hastexo/hastexo-xblock/tree/stable-0.5).


## Purpose

The hastexo XBlock orchestrates a virtual environment (a "stack") that runs on
an [OpenStack](https://www.openstack.org) private or public cloud using the
[OpenStack Heat](http://docs.openstack.org/developer/heat/) orchestration
engine. It provides a Secure Shell session directly within the courseware.

Stack creation is idempotent, so a fresh stack will be spun up only if it does
not already exist. An idle stack will auto-suspend after a configurable time
period, which is two minutes by default. The stack will resume automatically
when the student returns to the lab environment.

Since public cloud environments typically charge by the minute to *run*
virtual machines, the hastexo XBlock makes lab environments cost effective to
deploy. The hastexo XBlock can run a fully distributed virtual lab environment
for a course in [Ceph](http://ceph.com), OpenStack,
[Open vSwitch](http://openvswitch.org/) or
[fleet](https://coreos.com/using-coreos/clustering/) for approximately $25 per
month on a public cloud (assuming students use the environment for 1 hour per
day).

Course authors can fully define and customize the lab environment. It is only
limited by the feature set of OpenStack Heat.


## Deployment

The easiest way for platform administrators to deploy the hastexo XBlock and
its dependencies to an Open edX installation is to pip install it to the `edxapp`
virtualenv, and then to use the `hastexo_xblock` role included in the
[hastexo\_xblock branch](https://github.com/hastexo/edx-configuration/tree/hastexo/ginkgo/hastexo_xblock)
of `edx/configuration`.

To deploy the hastexo XBlock:

1. Install it via pip:

    ```
    $ sudo /edx/bin/pip.edxapp install hastexo-xblock
    ```

    > Do **not** run `pip install` with `--upgrade`, however, as this will
    > break edx-platform's own dependencies.

2. Collect static assets:

    ```
    $ sudo /edx/bin/edxapp-update-assets-lms
    ```

3. Add it to the `ADDL_INSTALLED_APPS` of your LMS environment, by editing
   `/edx/app/edxapp/lms.env.json` and adding:

    ```
    "ADDL_INSTALLED_APPS": [
        "hastexo"
    ],
    ```

4. This xblock uses a Django model to synchronize stack information across
   instances.  Migrate the `edxapp` database so the `hastexo_stack` table is
   created:

   ```
   $ sudo /edx/bin/edxapp-migrate-lms
   ```

5. Add configuration to `XBLOCK_SETTINGS` on `/edx/app/edxapp/lms.env.json`:

    ```
    "XBLOCK_SETTINGS": {
        "hastexo": {
            "terminal_url": "/hastexo-xblock/",
            "launch_timeout": 900,
            "suspend_timeout": 120,
            "suspend_interval": 60,
            "suspend_concurrency": 4,
            "suspend_in_parallel": true,
            "check_timeout": 120,
            "delete_interval": 86400,
            "delete_age": 14,
            "delete_attempts": 3,
            "task_timeouts": {
                "sleep": 10,
                "retries": 90
            },
            "js_timeouts": {
                "status": 15000,
                "keepalive": 30000,
                "idle": 3600000,
                "check": 5000
            },
            "providers": {
                "default": {
                    "os_auth_url": "",
                    "os_auth_token": "",
                    "os_username": "",
                    "os_password": "",
                    "os_user_id": "",
                    "os_user_domain_id": "",
                    "os_user_domain_name": "",
                    "os_project_id": "",
                    "os_project_name": "",
                    "os_project_domain_id": "",
                    "os_project_domain_name": "",
                    "os_region_name": ""
                },
                "provider2": {
                    "os_auth_url": "",
                    "os_auth_token": "",
                    "os_username": "",
                    "os_password": "",
                    "os_user_id": "",
                    "os_user_domain_id": "",
                    "os_user_domain_name": "",
                    "os_project_id": "",
                    "os_project_name": "",
                    "os_project_domain_id": "",
                    "os_project_domain_name": "",
                    "os_region_name": ""
                },
            }
        }
    }
    ```

6. Now install the Guacamole web app and stack supervisor scripts by cloning
   the `hastexo_xblock` fork of edx/configuration and assigning that role to
   the machine:

    ```
    $ git clone -b hastexo/ginkgo/hastexo_xblock https://github.com/hastexo/edx-configuration.git
    $ cd edx-configuration/playbooks
    $ ansible-playbook -c local -i "localhost," run_role.yml -e role=hastexo_xblock
    ```

7. At this point restart edxapp, its workers, and make sure the stack jobs are
   running:

    ```
    sudo /edx/bin/supervisorctl restart edxapp:
    sudo /edx/bin/supervisorctl restart edxapp_worker:
    sudo /edx/bin/supervisorctl start suspender:
    sudo /edx/bin/supervisorctl start reaper:
    ```

8. Finally, in your course, go to the advanced settings and add the hastexo
   module to the "Advanced Module List" like so:

   ```
   [
    "annotatable",
    "openassessment",
    "hastexo"
   ]
   ```


## XBlock settings

The hastexo XBlock must be configured via `XBLOCK_SETTINGS` in
`lms.env.json`, under the `hastexo` key.  At the very minimum, you must
configure a single "default" provider with the OpenStack credentials specific
to the cloud you will be using.  All other variables can be left at their
defaults.

This is a brief explanation of each:

* `terminal_url`: The URL path to the Guacamole web app.  It can be an absolute
  path, or start with a ":"-prefixed port (such as ":8080/hastexo-xblock/", for
  use in devstacks). (Default: `/hastexo-xblock/`)

* `launch_timeout`: How long to wait for a stack to be launched, in seconds.
  (Default: `900`)

* `suspend_timeout`: How long to wait before suspending a stack, after the last
  keepalive was received from the browser, in seconds.  (Default: `120`)

* `suspend_interval`: The period between suspend job launches. (Default: `60`)

* `suspend_concurrency`: How many stacks to suspend on each job run. (Default:
  `4`)

* `suspend_in_parallel`: Whether to suspend stacks in parallel. (Default: true)

* `check_timeout`: How long to wait before a check progress task fails.
  (Default: `120`)

* `delete_age`: Delete stacks that haven't been resumed in this many days.  Set
  to 0 to disable. (Default: 14)

* `delete_interval`: The period between reaper job launches. (Default:
  `3600`)

* `delete_attempts`: How many times to insist on deletion after a failure.
  (Default: `3`)

* `task_timeouts`:

    * `sleep`: How long to wait between stack checks, such as pings and SSH
      attempts, in seconds. (Default: `10`)

    * `retries`: How many times to retry stack checks, such as pings and SSH
      attempts. (Default: `90`)

* `js_timeouts`:

    * `status`: In the browser, when launching a stack, how long to wait
      between polling attempts until it is complete, in milliseconds (Default:
      `15000`)

    * `keepalive`: In the browser, after the stack is ready, how long to wait
      between keepalives to the server, in milliseconds. (Default: `30000`)

    * `idle`: In the browser, how long to wait until the user is considered
      idle, when no input is registered in the terminal, in milliseconds.
      (Default: `3600000`)

    * `check`: In the browser, after clicking "Check Progress", how long to
      wait between polling attempts, in milliseconds. (Default: `5000`)

* `providers`: A dictionary of OpenStack providers that course authors can pick
  from.  Each entry is itself a dictionary containing OpenStack credentials.
  You must configure at least one, named "default".  The following is a list
  of supported OpenStack credential variables:

    * `os_auth_url`
    * `os_auth_token`
    * `os_username`
    * `os_password`
    * `os_user_id`
    * `os_user_domain_id`
    * `os_user_domain_name`
    * `os_project_id`
    * `os_project_name`
    * `os_project_domain_id`
    * `os_project_domain_name`
    * `os_region_name`


## Creating a Heat template for your course

To use the hastexo XBlock, start by creating a Heat template and uploading it
to the content store.  The XBlock imposes some constraints on the template
(detailed below), but you are otherwise free to customize your training
environment as needed.  A sample template is provided under
`heat-templates/hot/openstack-sample.yaml`.

To ensure your Heat template has the required configuration:

1. Configure the Heat template to accept a "run" parameter, which will contain
   information about the course run where the XBlock is instanced.  This is
   intended to give course authors a way to, for example, tie this to a
   specific Glance image when launching VMs:

    ```
    run:
      type: string
      description: Stack run
    ```

2. Configure the Heat template to generate an SSH key pair dynamically and
   save the private key.  For example:

    ```
    training_key:
      type: OS::Nova::KeyPair
      properties:
        name: { get_param: 'OS::stack_name' }
        save_private_key: true
    ```

    In addition, if using RDP or VNC you must generate a random password and
    assign it to the stack user:

    ```
    stack_password:
      type: OS::Heat::RandomString
      properties:
        length: 32

    cloud_config:
      type: OS::Heat::CloudConfig
      properties:
        cloud_config:
          chpasswd:
            list:
              str_replace:
                template: "user:{password}"
                params:
                  "{password}": { get_resource: stack_password }
    ```

3. Configure the Heat template to have an instance that is publicly accessible
   via `floating_ip_address`.

4. Provide the following outputs with these exact names:

    ```
    outputs:
      public_ip:
        description: Floating IP address of deploy in public network
        value: { get_attr: [ deploy_floating_ip, floating_ip_address ] }
      private_key:
        description: Training private key
        value: { get_attr: [ training_key, private_key ] }
    ```

    If you generated a random password as described above, create an output as
    follows:

    ```
      password:
        description: Stack password
        value: { get_resource: stack_password }
    ```

    If you also provide a list of servers under an `reboot_on_resume` item, the
    servers listed therein will be hard rebooted after a resume operation:

    ```
      reboot_on_resume:
        description: Servers to be rebooted after resume
        value:
          - { get_resource: server1 }
          - { get_resource: server2 }
    ```

    (This is meant primarily as a workaround to resurrect servers that use
    nested KVM, as the latter does not support a managed save and subsequent
    restart.)

5. Upload the Heat template to the content store and make a note of its static
   asset file name.


## Using the hastexo XBlock in a course

To create a stack for a student and display a terminal window where invoked,
you need to define the `hastexo` tag in your course content.   It must be
configured with the following attributes:

* `stack_template_path`: The static asset path to a Heat template.

* `stack_user_name`: The name of the user that the Xblock will use to connect
  to the environment, as specified in the Heat template.

* `protocol`: One of 'ssh', 'rdp', or 'vnc'.  This defines the protocol that
  will be used to connect to the environment.  The default is 'ssh'.

* `provider`: (Optional) The name of an OpenStack provider configured in the
  platform.

* `stack_ports`: (Optional) A list of port numbers the user can choose from.
  This is intended as a means of providing a way to connect directly to
  multiple VMs in a lab environment, via port forwarding or proxying at the VM
  with the public IP address.

* `stack_port_names`: (Optional) A list of user-friendly names that will be
  shown as a dropdown to the user.  It must match the list of port numbers in
  both order and number.


For example, in XML:

```
<vertical url_name="lab_introduction">
  <hastexo
    url_name="lab_introduction"
    stack_template_path="hot_lab.yaml"
    stack_user_name="training"
    protocol="rdp"
    provider="default"
    stack_ports="[3389, 3390]"
    stack_port_names="['server1', 'server2']" />
</vertical>
```

**Important**: Do this only *once per section*. Defining it more that once
per section is not supported.

In order to add the hastexo Xblock through Studio, open the unit where you want
it to go.  Add a new component, select `Advanced`, then select the `Lab`
component.  This adds the XBlock.  Edit the Settings as explained above.


## Student experience

When students navigate to a unit with a hastexo XBlock in it, a new Heat
stack will be created (or resumed) for them. The Heat stack will be as defined
in the uploaded Heat template. It is unique per student and per course run. If
the same tag appears on a different course, or different run of the same
course, the student will get a different stack.

The stack will suspend if the student does not navigate to the `hastexo` unit
in that section within the default two minutes (configurable via settings, as
explained above). When the student gets to the `hastexo` unit, the stack will
be resumed and they will be connected automatically and securely. They will not
need a username, password, or host prompts to their personal lab environment.
This happens transparently in the browser.

The student can work at their own pace in their environment. However, when
a student closes the browser where the `hastexo` unit is displayed, or if they
put their computer to sleep, a countdown is started. If the student does not
reopen the environment within two minutes their stack will be suspended. When
a student comes back to the lab environment to finish the exercise, their
stack is resumed automatically.  They are connected to the same training
environment they were working with before, in the *same state* they left it in.
(The process of suspension works just like in a home computer.)


## Usage in devstack

It is possible to use this XBlock in devstack.  To do so, however, requires
tweaking a few settings.

First, due to the fact that in a devstack, by default all Celery calls are
synchronous, scheduled tasks are executed immediately.  This means that with
default settings, tasks will be immediately suspended.  To fix this, suspension
must be disabled.  In addition, since Ajax calls from the browser are also
synchronous in devstack (i.e., the connection remains open until the task is
complete), the Javascript timeouts don't make sense.

Also, devstacks don't install nginx.  Therefore, the Guacamole app is only
reachable directly at its configured port.  This means that `terminal_url` in
the XBlock settings must be set to that port (by default, 8080).

These are the recommended devstack settings for `/edx/app/edxapp/lms.env.json`
(OpenStack providers have been omitted):

    ```
    "XBLOCK_SETTINGS": {
        "hastexo": {
            "terminal_url": ":8080/hastexo-xblock/"
            "launch_timeout": 0,
            "suspend_timeout": 0,
            "task_timeouts": {
                "sleep": 10,
                "retries": 90
            },
            "js_timeouts": {
                "status": 0,
                "keepalive": 0,
                "idle": 0,
                "check": 0
            },
        }
    }
    ```

However, it is also possible to run this XBlock asynchronously in a devstack.  To do
so, keep the XBlock settings at their defaults (i.e., with non-zero timeouts),
open three terminal windows, and run each of the following concurrently:

    ```
    paver devstack lms --settings=devstack_with_worker
    ./manage.py lms celery worker --settings=devstack_with_worker -l DEBUG
    ./manage.py lms --settings=devstack_with_worker suspender
    ./manage.py lms --settings=devstack_with_worker reaper
    ```


## Running tests

The testing framework is built on
[tox](https://tox.readthedocs.io/). After installing tox, you can
simply run `tox` from your Git checkout of this repository.

In addition, you can run `tox -r` to throw away and rebuild the
testing virtualenv, or `tox -e flake8` to run only PEP-8 checks, as
opposed to the full test suite.


## License

This XBlock is licensed under the Affero GPL; see [`LICENSE`](LICENSE)
for details.
