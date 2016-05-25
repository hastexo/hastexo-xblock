# hastexo XBlock

The hastexo [XBlock](https://xblock.readthedocs.org/en/latest/) is an
[Open edX](https://open.edx.org/) API that integrates realistic lab
environments into distributed computing courses. The hastexo XBlock allows
students to access an OpenStack environment within an edX course.


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
its dependencies to an Open edX installation is to pip install it to the edxapp
virtualenv, and then to use the `gateone` role included in [hastexo's
fork](https://github.com/hastexo/edx-configuration/tree/hastexo/master/hastexo)
of `edx/configuration`.

To deploy the hastexo XBlock:

1. Install it via pip:

    ```
    $ sudo /edx/bin/pip.edxapp install -e git+https://github.com/hastexo/hastexo-xblock.git@master#egg=hastexo-xblock
    ```

2. Add it to the `ADDL_INSTALLED_APPS` of your LMS environment, by editing
   `/edx/app/edxapp/lms.env.json` and adding:

    ```
    "ADDL_INSTALLED_APPS": [
        "hastexo"
    ],
    ```

3. Now install gateone by cloning the hastexo fork of edx/configuration and
   assigning that role to the machine:

    ```
    $ git clone -b hastexo/master/base https://github.com/hastexo/edx-configuration.git
    $ cd edx-configuration/playbooks
    $ ansible-playbook -c local -i "localhost," run_role.yml -e role=gateone
    ```

4. Finally, restart edxapp and its workers:

    ```
    sudo /edx/bin/supervisorctl restart edxapp:
    sudo /edx/bin/supervisorctl restart edxapp_worker:
    ```

5. In your course, go to the advanced settings and add the hastexo module to 
   the "Advanced Module List" like so:
   ```
   [
    "annotatable",
    "videoalpha",
    "openassessment",
    "hastexo"
   ]
   ```



## Configuration

To use the hastexo XBlock upload a Heat template to the content store. There
are some limitations to the configuration of the Heat template (detailed
below), but otherwise you can customize your training environment as
you like. A sample template is provided under `heat-templates/hot/openstack-sample.yaml`.

To ensure your Heat template has the required configuration:

1. Upload a Heat template to the content store and make a note of its static
   asset file name.

2. Configure the Heat template to generate an SSH key pair dynamically and
   save the private key.  For example:

    ```
    training_key:
      type: OS::Nova::KeyPair
      properties:
        name: { get_param: 'OS::stack_name' }
        save_private_key: true
    ```

2. Configure the Heat template to have an instance that is publicly accessible
   on the internet via `floating_ip_address`.

3. Provide the above two items as outputs, with the following names:

    ```
    outputs:
      public_ip:
        description: Floating IP address of deploy in public network
        value: { get_attr: [ deploy_floating_ip, floating_ip_address ] }
      private_key:
        description: Training private key
        value: { get_attr: [ training_key, private_key ] }
    ```

To create a stack for a student and display a terminal window where invoked,
you need to define the `hastexo` tag in your course content with the following
information:

* The credentials for the public or private OpenStack cloud
* The static asset path to markdown lab instructions
* The static asset path to a Heat template
* The name of the user that the Xblock will use to connect to the environment
  via SSH.

```
<vertical url_name="lab_introduction">
  <hastexo
    url_name="lab_introduction"
    instructions_path="markdown_lab.md"
    stack_template_path="hot_lab.yaml"
    stack_user_name="training"
    os_auth_url="https://os.auth.url:5000/v2.0"
    os_tenant_name="example.com"
    os_username="demo@example.com"
    os_password="foobarfoobarfoofoo" />
</vertical>
```

**Important**: Do this only *once per section*. Defining it more that once
per section has undefined behavior.

In order to add the Hastexo Xblock through Studio, open the (sub)unit where
you want it to appear. Add a new component and select `Advanced`, then select 
the `Lab` component. This adds the XBlock. Edit the Settings to add the various
OpenStack variables.


## Student Experience

When students navigate to a unit with a hastexo XBlock in it, a new Heat
stack will be created (or resumed) for them. The Heat stack will be as defined
in the uploaded Heat template. It is unique per student and per course run. If
the same tag appears on a different course, or different run of the same
course, the student will get a different stack.

The stack will suspend if the student does not navigate to the `hastexo` unit
in that section within two minutes. When the student gets to the `hastexo`
unit, the stack will be resumed and they will be connected automatically and
securely. They will not need a username, password, or host prompts to their
personal lab environment. This happens transparently in the browser.

The student can work at their own pace in their environment. However, when
a student closes the browser where the `hastexo` unit is displayed, or if they
put their computer to sleep, a countdown is started. If the student does not
reopen the environment within two minutes their stack will be suspended. When
a student comes back to the lab environment to finish the exercise, their
stack is resumed automatically.  They are connected to the same training
environment they were working with before, in the *same state* they left it in.

## Running tests

For now, one must run the provided unit tests (which are currently limited to
tasks) from the edxapp virtualenv, as deployed by fullstack.  Thus, on such a
box:

```
$ sudo /edx/bin/python.edxapp -m unittest hastexo.tests.unit.test_tasks
```

Or,

```
$ cd /edx/app/edxapp/hastexo-xblock
$ /edx/app/edxapp/venvs/edxapp/bin/nosetests hastexo/tests -v
```

## License

This XBlock is licensed under the Affero GPL; see [`LICENSE`](LICENSE)
for details.
