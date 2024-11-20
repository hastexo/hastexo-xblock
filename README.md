[![PyPI version](https://badge.fury.io/py/hastexo-xblock.svg)](https://pypi.python.org/pypi/hastexo-xblock)
[![Build Status](https://github.com/hastexo/hastexo-xblock/workflows/Python%20package/badge.svg)](https://github.com/hastexo/hastexo-xblock/actions?query=workflow%3A%22Python+package%22) [![codecov](https://codecov.io/gh/hastexo/hastexo-xblock/branch/master/graph/badge.svg)](https://codecov.io/gh/hastexo/hastexo-xblock)

# hastexo XBlock

The hastexo [XBlock](https://xblock.readthedocs.org/en/latest/) is an
[Open edX](https://open.edx.org/) API that integrates realistic lab
environments into distributed computing courses. The hastexo XBlock
allows students to access an OpenStack (or Google Cloud) environment
within an edX course.

It leverages [Apache Guacamole](https://guacamole.incubator.apache.org/) as a
browser-based connection mechanism, which includes the ability to connect to
graphical user environments (via VNC and RDP), in addition to terminals (via
SSH).

## Version compatibility matrix

You must install a supported release of this XBlock to match the
Open edX and [Tutor](https://docs.tutor.overhang.io/) version you are
deploying. If you are installing this plugin from a branch in this Git
repository, you must select the appropriate one:

| Open edX release | Tutor version | XBlock version | XBlock branch |
|------------------|---------------|----------------|---------------|
| Maple            | `>=13.2, <14` | `>=6.0, <7.0`  | `stable-6.0`  |
| Nutmeg           | `>=14.0, <15` | `>=7.0, <8.0`  | `stable-7`    |
| Olive            | `>=15.0, <16` | `>=7.5, <8.0`  | `stable-7`    |
| Palm             | `>=16.0, <17` | `>=7.5, <8.0`  | `stable-7`    |
| Quince           | `>=17.0, <18` | `>=7.9, <8.0`  | `stable-7`    |
| Redwood          | `>=18.0, <19` | `>=8.0`        | `master`      |

Instructions for deploying this XBlock with Tutor can be found
below, in the [Deployment with Tutor](#deployment-with-tutor)
section.

## Purpose

The hastexo XBlock orchestrates a virtual environment (a "stack") that runs on
a private or public cloud (currently [OpenStack](https://www.openstack.org) or
[Gcloud](https://cloud.google.com/)) using its orchestration engine. It
provides a Secure Shell session directly within the courseware.

Stack creation is idempotent, so a fresh stack will be spun up only if it does
not already exist. An idle stack will auto-suspend after a configurable time
period, which is two minutes by default. The stack will resume automatically
when the student returns to the lab environment.

Since public cloud environments typically charge by the minute to *run*
virtual machines, the hastexo XBlock makes lab environments cost effective to
deploy. The hastexo XBlock can run a fully distributed virtual lab environment
for a course in [Ceph](http://ceph.com), OpenStack, or
[Open vSwitch](http://openvswitch.org/) for approximately $25 per
month on a public cloud (assuming students use the environment for 1 hour per
day).

Course authors can fully define and customize the lab environment. It is only
limited by the feature set of the cloud's deployment features.


## Deployment with [Tutor](https://docs.tutor.overhang.io)

Running this XBlock with Tutor (for Open edX Maple and later) requires
two steps:

1. Install the XBlock to your Tutor environment by adding it to the
   `OPENEDX_EXTRA_PIP_REQUIREMENTS` list in `config.yml`:
   ```
   OPENEDX_EXTRA_PIP_REQUIREMENTS:
     - "hastexo-xblock==8.1.0"
   ```
   For additional information, please refer to the [official
   documentation](https://docs.tutor.overhang.io/configuration.html#installing-extra-xblocks-and-requirements).


2. Install and enable the `tutor-contrib-hastexo` plugin:
   ```
   pip install git+https://github.com/hastexo/tutor-contrib-hastexo
   tutor plugins enable hastexo
   ```
   Add the necessary configurations to your Tutor `config.yml`. Unless
   you want to change the default configurations, you'll only need to
   add the settings for the XBlock via `HASTEXO_XBLOCK_SETTINGS`, for
   example:
   ```
   HASTEXO_XBLOCK_SETTINGS:
     check_timeout: 120
     delete_age: 0
     delete_attempts: 3
     delete_interval: 3600
     delete_task_timeout: 900
     guacamole_js_version: 1.5.4
     enable_fullscreen: false
     instructions_layout: above
     js_timeouts:
       check: 5000
       idle: 3600000
       keepalive: 30000
       status: 15000
     launch_timeout: 900
     providers:
       default:
         type: openstack
         os_auth_url: ""
         os_auth_token: ""
         os_username: ""
         os_password: ""
         os_user_id: ""
         os_user_domain_id: ""
         os_user_domain_name: ""
         os_project_id: ""
         os_project_name: ""
         os_project_domain_id: ""
         os_project_domain_name: ""
         os_region_name: ""
       provider2:
         type: "gcloud"
         gc_type: "service_account"
         gc_project_id: ""
         gc_private_key_id: ""
         gc_private_key: ""
         gc_client_email: ""
         gc_client_id: ""
         gc_auth_uri: ""
         gc_token_uri: ""
         gc_auth_provider_x509_cert_url: ""
         gc_client_x509_cert_url: ""
         gc_region_id: ""
     remote_exec_timeout: 300
     sleep_timeout: 10
     suspend_concurrency: 4
     suspend_interval: 60
     suspend_task_timeout: 900
     suspend_timeout: 120
     terminal_color_scheme: white-black
     terminal_font_name: monospace
     terminal_font_size: '10'
     terminal_url: /hastexo-xblock/
   ```
   For more details about each setting, please refer to [the *XBlock
   settings* section](#xblock-settings) below.

3. Before deploying services with Tutor, build the Docker image for
   the `hastexo` service, and also build a custom `openedx` image:
   ```
   tutor images build openedx hastexo
   ```
   For more information about the plugin configuration, please refer
   to [the plugin
   README](https://github.com/hastexo/tutor-contrib-hastexo).

4. After you have deployed Open edX with Tutor, your platform is
   operational, and you have created a course in Open edX Studio, go
   to *Settings* → *Advanced Settings* and add the `hastexo` module to
   *Advanced Module List,* like so:
   ```
   [
    "annotatable",
    "openassessment",
    "hastexo"
   ]
   ```

## XBlock settings

The hastexo XBlock must be configured via `XBLOCK_SETTINGS` in
`lms.env.json` (or `lms.yml), under the `hastexo` key.  At the very
minimum, you must configure a single "default" provider with the
credentials specific to the cloud you will be using.  All other
variables can be left at their defaults.

This is a brief explanation of each:

* `terminal_url`: URL to the Guacamole web app.  If it is defined with a fully
  qualified domain, it must include the protocol (`http://` or `https://`).  If
  not, it is assumed to be an absolute path based on the current
  `window.location`.  (It is possible to define it with a ":"-prefixed port,
  such as ":8080/hastexo-xblock/", for use in devstacks). (Default:
  `/hastexo-xblock/`)

* `terminal_color_scheme`: Color scheme for the terminal window. Suitable values
  are described in [Guacamole Documentation](https://guacamole.apache.org/doc/gug/configuring-guacamole.html#ssh).
  For example, `foreground:rgb:ff/ff/ff;background:rgb:00/00/00` and
  `white-black` both represent white text on a black background.
  (Default: `white-black`)

* `terminal_font_name`: The name of the font to use in terminal. A matching font
  must be installed on the Guacamole server. (Default: `monospace`) 

* `terminal_font_size`: The size of the font to use in terminal, in points.
  (Default: `10`)

* `instructions_layout`: Configuration for instructions layout. It's possible
  to set the position for instructions to be 'above', 'below', 'left' or 'right'
  from the terminal window. (Default: `above`; this is currently an
  experimental feature)

* `enable_fullscreen`: An option to allow learners to launch a lab in fullsceen mode,
  in a separate browser window. (Default: `false`)

* `lab_usage_limit`: Allocate limited time per user for labs across the platform,
  in seconds. (Default is `None`, meaning there is no time limit).

* `lab_usage_limit_breach_policy`: What to do when the learner's lab
  limit has been exceeded.

  * `None` (the default) means just write a message to the logs.

  * `warn` will display a warning to the learner that the
  limit has been reached, but does allow them to keep using the labs.

  * `block` blocks the learner's access to the lab.

* `launch_timeout`: How long to wait for a stack to be launched, in seconds.
  (Default: `900`)

* `remote_exec_timeout`: How long to wait for a command to be executed remotely
  over SSH, in seconds.  (Default: `300`)

* `suspend_timeout`: How long to wait before suspending a stack, after the last
  keepalive was received from the browser, in seconds.  (Default: `120`)

* `suspend_interval`: The period between suspend job launches. (Default: `60`)

* `suspend_concurrency`: How many stacks to suspend on each job run. (Default:
  `4`)

* `suspend_task_timeout`: How long to wait for a stack to be suspended, in
  seconds.  (Default: `900`)

* `check_timeout`: How long to wait before a check progress task fails.
  (Default: `120`)

* `delete_age`: Delete stacks that haven't been resumed in this many days.  Set
  to 0 to disable. (Default: 14)

* `delete_interval`: The period between reaper job launches. (Default:
  `3600`)

* `delete_attempts`: How many times to insist on deletion after a failure.
  (Default: `3`)

* `delete_task_timeout`: How long to wait for a stack to be deleted, in
  seconds.  (Default: `900`)

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
  from.  Each entry is itself a dictionary containing provider configuration
  parameters.  You must configure at least one, named "default".  The following
  is a list of supported parameters:

    * `type`: The provider type.  Currently "openstack" or "gcloud".  Defaults
      to "openstack" if not provided, for backwards-compatibility.

    The following apply to OpenStack only:

    * `os_auth_url`: OpenStack auth URL.

    * `os_auth_token`: OpenStack auth token.

    * `os_username`: OpenStack user name.

    * `os_password`: OpenStack password.

    * `os_user_id`: OpenStack user id.

    * `os_user_domain_id`: OpenStack domain id.

    * `os_user_domain_name`: OpenStack domain name.

    * `os_project_id`: OpenStack project id.

    * `os_project_name`: OpenStack project name.

    * `os_project_domain_id`: OpenStack project domain id.

    * `os_project_domain_name`: OpenStack project domain name.

    * `os_region_name`: OpenStack region name.

    The following apply to Gcloud only.  All values aside from region can be
    obtained by creating a [service
    account](https://console.developers.google.com/iam-admin/serviceaccounts)
    and downloading the JSON-format key:

    * `gc_deploymentmanager_api_version`: The deployment service api version.
      (Default: "v2")

    * `gc_compute_api_version`: The compute service api version. (Default: "v1")

    * `gc_type`: The type of account, currently only `service_account`.

    * `gc_project_id`: Gcloud project ID.

    * `gc_private_key_id`: Gcloud private key ID.

    * `gc_private_key`: Gcloud private key, in its entirety.

    * `gc_client_email`: Gcloud client email.

    * `gc_client_id`: Gcloud cliend ID.

    * `gc_auth_uri`: Gcloud auth URI.

    * `gc_token_uri`: Gcloud token URI.

    * `gc_auth_provider_x509_cert_url`: Gcloud auth provider cert URL.

    * `gc_client_x509_cert_url`: Gcloud client cert URL.

    * `gc_region_id`: Gcloud region where labs will be launched.


## Creating an orchestration template for your course

To use the hastexo XBlock, start by creating an orchestration template and
uploading it to the content store.  The XBlock imposes some constraints on the
template (detailed below), but you are otherwise free to customize your
training environment as needed.

To ensure your template has the required configuration:

1. Configure the template to accept a "run" parameter, which will contain
   information about the course run where the XBlock is instanced.  This is
   intended to give course authors a way to, for example, tie this to a
   specific virtual image when launching VMs.

2. If your orchestration engine allows it, configure the template to generate
   an SSH key pair dynamically and save the private key.

3. In addition, if using RDP or VNC you must generate a random password and
   assign it to the stack user.

4. Configure the template to have at least one instance that is publicly
   accessible via an IPv4 address.

5. Provide the following outputs with these exact names:

    * `public_ip`: The publically accessible instance.

    * `private_key`: The generated passphrase-less SSH private key.

    * `password`: The generated password. (OPTIONAL)

    * `reboot_on_resume`: A list of servers to be rebooted upon resume.  This
      is meant primarily as a workaround to resurrect servers that use nested
      KVM, as the latter does not support a managed save and subsequent
      restart. (OPTIONAL, DEPRECATED)

6. Upload the template to the content store and make a note of its static asset
   file name.

### Heat examples

A sample Heat template is provided under `samples/hot/sample-template.yaml`.

Accepting the run parameter:

    ```
    run:
      type: string
      description: Stack run
    ```

Generating an SSH key pair:

    ```
    training_key:
      type: OS::Nova::KeyPair
      properties:
        name: { get_param: 'OS::stack_name' }
        save_private_key: true
    ```

Generating a random password and setting it:

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

Defining the outputs:

    ```
    outputs:
      public_ip:
        description: Floating IP address of deploy in public network
        value: { get_attr: [ deploy_floating_ip, floating_ip_address ] }
      private_key:
        description: Training private key
        value: { get_attr: [ training_key, private_key ] }
      password:
        description: Stack password
        value: { get_resource: stack_password }
      reboot_on_resume:
        description: Servers to be rebooted after resume
        value:
          - { get_resource: server1 }
          - { get_resource: server2 }
    ```

### Gcloud examples

A sample Gcloud template is provided under `samples/gcloud/sample-template.yaml.jinja`.

The Gcloud deployment manager cannot generate an SSH key or random password
itself, so the XBlock will do it for you.  There's no need to generate them or
provide outputs manually.  However, you do need to make use of the ones
provided as properties:

    ```
    resources:
      - name: {{ env["deployment"] }}-server
        type: compute.v1.instance
        properties:
          metadata:
           items:
           - key: user-data
             value: |
               #cloud-config
               users:
                 - default
                 - name: training
                   gecos: Training User
                   groups: users,adm
                   ssh-authorized-keys:
                     - ssh-rsa {{ properties["public_key"] }}
                   lock-passwd: false
                   shell: /bin/false
                   sudo: ALL=(ALL) NOPASSWD:ALL
               chpasswd:
                 list: |
                   training:{{ properties["password"] }}
           runcmd:
             - echo "exec /usr/bin/screen -xRR" >> /home/training/.profile
             - echo {{ properties["private_key"] }} | base64 -d > /home/training/.ssh/id_rsa
    ```

Note that due to the fact that the deployment manager does not accept property
values with multiple lines, the private key is base64-encoded.

As for outputs, in a Gcloud template one needs only one:

    ```
    outputs:
    - name: public_ip
      value: $(ref.{{ env["deployment"] }}-server.networkInterfaces[0].accessConfigs[0].natIP)
    ```


## Using the hastexo XBlock in a course

To create a stack for a student and display a terminal window where invoked,
you need to define the `hastexo` tag in your course content.   It must be
configured with the following attributes:

* `stack_user_name`: The name of the user that the Xblock will use to connect
  to the environment, as specified in the orchestration template.

The following are optional:

* `stack_protocol`: One of `ssh`, `rdp`, or `vnc`. This defines the
  protocol that will be used to connect to the environment. The
  default is `ssh`.

* `stack_template_path`: The static asset path to the orchestration template,
  if not specified per provider below.

* `stack_key_type`: An SSH key type for accessing the lab environment.
  Options are `rsa`, `ed25519` and `""` (default). If a key type is chosen,
  a key with the selected type will be generated for the lab environment.
  If set to an empty string, the key handling should be done via the lab template.

* `launch_timeout`: How long to wait for a stack to be launched, in seconds.
  If unset, the global timeout will be used.

* `suspend_timeout`: Timeout for how long to wait before suspending a stack,
  after the last keepalive was received from the browser, in seconds.
  Takes precedence over the globally defined timeout."

* `delete_age`: Delete stacks that haven't been resumed in this many seconds.
  Overrides the globally defined setting. The global setting currently only
  supports days but will begin to support suffixes `d`, `h`, `m`, `s` in future
  releases. Using this attribute will allow setting the `delete_age` value per
  instance and configure it to have a shorter value.

* `read_only`: Display a lab terminal in a `read-only` mode. If set to `True`,
  a lab stack will be created or resumed as usual, the student can see the lab
  terminal but is not able to interact with it. Default is `False`.

* `hidden`: An option to hide the lab itself in the browser while spinning up
  the lab environment in the background. Default is `False`.

* `enable_fullscreen`: An option to allow learners to launch a lab in fullsceen mode,
  in a separate browser window. If used, overrides the globally defined setting.
  Options are "true", "false" and "inherit". Default is "inherit" (to use global value).

* `progress_check_label`: Set a label for the progress check button.
  For example: `Submit Answer` or `Check Progress` (Default).

* `show_feedback`: On progress check, show feedback on how many tasks out of total 
  are completed. Default is `True`.

* `show_hints_on_error`: On progress check failure, display the tests' standard
  error streams as hints.
  When `show_feedback` is set to `False`, hints will never be displayed and having
  this set to `True` will have no effect. Default is `True`.

* `progress_check_result_heading`: Message to display on progress check result window.
  This could be set to "Answer Submitted" for example, when choosing to not display
  hints and feedback. Default is "Progress check result".

You can also use the following nested XML options:

* `providers`: A list of references to providers configured in the platform.
  Each `name` attribute must match one of the providers in the XBlock
  configuration. `capacity` specifies how many environments should be launched
  in that provider at maximum (where "-1" means keep launching environments
  until encountering a launch failure, and "0" disables the provider).
  `template` is the content store path to the orchestration template (if not
  given, `stack_template_path` will be used).  `environment` specifies a
  content store path to a either a Heat environment file, or, if using Gcloud,
  a YAML list of properties.  If no providers are specified, the platform
  default will be used.

* `ports`: A list of ports the user can manually choose to connect to.  This is
  intended as a means of providing a way to connect directly to multiple VMs in
  a lab environment, via port forwarding or proxying at the VM with the public
  IP address.  Each `name` attribute will be visible to the user.  The `number`
  attribute specifies the corresponding port.

* `tests`: A list of test scripts.  The contents of each element will be run
  verbatim a a script in the user's lab environment, when they click the "Check
  Progress" button.  As such, each script should define an interpreter via the
  "shebang" convention.  If any scripts fail with a retval greater than 0, the
  learner gets a partial score for this instance of the XBlock.  In this case,
  the `stderr` of failed scripts will be displayed to the learner as a list of
  hints on how to proceed.

For example, in XML:

```
<vertical url_name="lab_introduction">
  <hastexo xmlns:option="http://code.edx.org/xblock/option"
    url_name="lab_introduction"
    stack_user_name="training"
    stack_protocol="rdp">
    <option:providers>
      - name: provider1
        capacity: 20
        template: hot_lab1_template.yaml
        environment: hot_lab1_env.yaml
      - name: provider2
        capacity: 30
        template: gcloud_lab1_template.yaml
        environment: gcloud_lab1_config.yaml
    </option:providers>
    <option:ports>
      - name: server1
        number: 3389
      - name: server2
        number: 3390
    </option:ports>
    <option:tests><![CDATA[
      - |
        #!/bin/bash
        # Check for login on vm1
        logins=$(ssh vm1 last root | grep root | wc -l)
        if [ $logins -lt 1 ]; then
          # Output a hint to stderr
          echo "You haven't logged in to vm1, yet." >&2
          exit 1
        fi
        exit 0
      - |
        #!/bin/bash
        # Check for file
        file=foobar
        if [ ! -e ${file} ]; then
          # Output a hint to stderr
          echo "File \"${file}\" doesn't exist." >&2
          exit 1
        fi
        exit 0
    ]]></option:tests>
  </hastexo>
</vertical>
```

**Important**: Do this only *once per section*. Defining it more than once
per section is not supported.

Note on tests: as seen in the above example, it is recommended to wrap them all
in `<![CDATA[..]]>` tags.  This avoids XML parsing errors when special
characters are encountered, such as the `>&2` used to output to stderr in bash.

In order to add the hastexo Xblock through Studio, open the unit where you want
it to go.  Add a new component, select `Advanced`, then select the `Lab`
component.  This adds the XBlock.  Edit the Settings as explained above.

### Using the hastexo XBlock in a content library

This XBlock is usable in [content libraries](https://edx.readthedocs.io/projects/open-edx-building-and-running-a-course/en/latest/course_components/libraries.html).
It supports adding lab instructions as child blocks, so that when the block is
randomized, the instructions are bundled together with it.

To add the XBlock to the library via Studio, make sure it is configured as one
of the `ADVANCED_PROBLEM_TYPES` in `cms.env.json`, then select it as such when
adding content to your library.  (Note: as of Open edX Ironwood, the ability to
do so requires running a [patched version](https://github.com/hastexo/edx-platform/tree/hastexo/ironwood/free_the_library)
of `edx-platform`.)

The following child block types are currently supported:

    * html
    * video
    * [pdf](https://github.com/MarCnu/pdfXBlock)

If using OLX, html blocks can be defined separately in the `html` subdirectory
as usual, with the child element referring to it by URL name:

```
<vertical url_name="lab_introduction">
  <hastexo ...>
    <html url_name="lab_instructions">
  </hastexo>
</vertical>
```

Child blocks will always be rendered _above_ the terminal.

### Using the hastexo XBlock while masquerading as a specific learner

Instructors can use the hastexo XBlock lab environments when masquerading as a specific learner by using the "View this course as:" option in the LMS staff header.

The learner will not know when an instructor is using their lab, so we advise to be mindful of the changes you make while the learner is active at the same lab.

This feature should be considered experimental, and is subject to future change or removal.

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

### Copy & paste

Within the text terminal, learners can use copy and paste by marking
up text with the left mouse button, and then using right-click or
middle-click to paste.

Within the graphical (RDP) terminal, so long as the terminal has focus
(normally meaning that the learner has left-clicked into it once),
learners can use any copy and paste facility that the desktop
provides. This includes the `Ctrl‑C`/`Ctrl‑V` key combinations, and
middle mouse clicks.

Copy & paste to and from the lab environment (i.e. from the terminal
to the learner's browser, or vice versa) is also possible, though some
considerations apply.

Pasting _into_ the lab environment requires two transitions, because
we are dealing with two clipboards (one for the browser and one for
the lab environment). Thus, the learner must

1. Copy something into their clipboard on their client.
2. Left-click into the terminal.
3. Hit `Ctrl‑V`. (This is the first transition, which populates the
   terminal's clipboard.)
4. Right-click, middle-click, or type `Ctrl‑Shift‑V` in the
   terminal. (This is the second transition, which pastes from the
   terminal's clipboard.)

Copying _out_ from the lab environment is more direct, though at this
time it works only on Mozilla Firefox (support in other browsers may
follow). To copy from their terminal into their local clipboard, the
learner must

1. Mark up some text in their terminal.
2. Switch to another application window on their client.
3. Hit `Ctrl‑V`.


## Django admin page

To facilitate management of stack states without direct access to the database,
a Django admin page is provided as a frontend for the `hastexo_stack` table.
To access it, go to the following as a superuser:

https://lms.example.com/admin/hastexo/stack

The following features are currently implemented:

* Searching: Search for a stack's name, course ID, status, and provider.

* Filtering: On the filter tab to the right, it is possible to select from a
  preset list of three filters: `course_id`, `status`, and `provider`.  The
  preset values are generated on the fly from existing records.

* On-list editing: modify multiple stack's states or providers directly from
  the main list.

* Marking stacks as deleted in bulk: to quickly change multiple stack states to
  `DELETE_COMPLETE`, and to reset their providers to "", select multiple stacks
  and use the "Mark selected stacks as DELETE_COMPLETE" action from the action
  dropdown.

* Displaying owner's email: when opening a stack's edit form (by clicking on
  its name), the owner's email is displayed.

When changing providers, only the ones enabled by the author for the course in
question are displayed.  If none are present, then the list is expanded with
the full set of providers configured in the platform.

The list of states is similarly limited to a known set of possibilities, but no
further validation is made.

Furthermore, the following are not currently possible:

* Displaying the owner's email on the main list

* Searching for a stack owner's email

* Adding a stack record

Note that making changes to the `hastexo_stack` table does not affect the
stacks themselves.  In other words, deleting an existing stack here will merely
delete its database record: not only will the stack itself continue to exist,
but the XBlock will cease to handle it automatically (such as suspending or
deleting it) until such time as the learner relaunches it.  The admin page is
only offered as a convenient way to manually synchronize the database with
actual stack states in case of failure.  It should not be necessary to do so in
day-to-day usage of the XBlock.


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
