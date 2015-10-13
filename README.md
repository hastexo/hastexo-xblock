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

Open edX platform administrators can deploy the hastexo Xblock to a previously
installed Open edX node or cluster by using the `hastexo_xblock` role and
accompanying `hastexo_xblock.yml` playbook included in
[hastexo's fork](https://github.com/hastexo/edx-configuration/tree/integration/cypress)
of `edx/configuration`. The hastexo XBlock role depends on modifications to
`edx/configuration` that are yet to be accepted upstream, so it must be run
from this fork.

To deploy the hastexo XBlock:

1. Clone hastexo's fork to your local repository.

2. For Open edX running on a single node, run:

```
$ cd edx-configuration/playbooks

$ ansible-playbook hastexo_xblock.yml \
  -e hastexo_xblock_repo=https://github.com/hastexo/hastexo-xblock.git \
  -e hastexo_xblock_version=cypress \
  --tags edxapp_cfg
```

   For Open edX running on OpenStack that uses multiple nodes (for example,
   the multi-node Heat template provided same hastexo fork of
   `edx/configuration`), limit the run to only the app servers:

```
$ cd edx-configuration/playbooks

$ ansible-playbook -i openstack/inventory.py hastexo_xblock.yml \
  -e hastexo_xblock_repo=https://github.com/hastexo/hastexo-xblock.git \
  -e hastexo_xblock_version=cypress \
  --tags edxapp_cfg \
  --limit app_servers
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
* The static asset path to your Heat template
* The name of the user that the Xblock will use to connect to the environment
  via SSH.

```
<vertical url_name="lab_introduction">
  <hastexo
    url_name="lab_introduction"
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

## Student Experience

When students navigate to a section with a `hastexo` unit in it, a new Heat
stack will be created (or resumed) for them, even if the student is not
looking at the `hastexo` unit itself. The Heat stack will be as defined in the
uploaded Heat template. It is unique per student and per course run. If the
same tag appears on a different course, or different run of the same course,
the student will get a different stack.

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


## License

This XBlock is licensed under the Affero GPL; see [`LICENSE`](LICENSE)
for details.
