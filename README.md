# hastexo-xblock

An [Open edX](https://open.edx.org/)
[XBlock](https://xblock.readthedocs.org/en/latest/) to integrate
realistic lab environments covering distributed computing
topics. Makes edX talk to OpenStack.


## What it does

This XBlock allows course authors to integrate arbitrarily complex
computing environments into lab exercises. It orchestrates a virtual
environment (a "stack") running on an
[OpenStack](https://www.openstack.org) private or public cloud (using
the [OpenStack Heat](http://docs.openstack.org/developer/heat/)
orchestration engine), and then provides a Secure Shell session right
inside the courseware. Stack creation is idempotent, so a fresh stack
will only be spun up if it does not already exist. An idle stack will
auto-suspend after a configurable time period (two minutes by
default), and will auto-resume as soon as the user returns to the lab.

Since public cloud environments typically charge by the minute for
*running* VMs, this makes the XBlock very cost-effective to deploy. A
fully distributed virtual environment to teach the likes of
[Ceph](http://ceph.com), OpenStack,
[Open vSwitch](http://openvswitch.org/) or
[fleet](https://coreos.com/using-coreos/clustering/) could be run at a
cost of approx. $25/month on a public cloud, assuming students spend
about 1 hour per day on the environment.

Course authors have full freedom in definining and customizing their
lab environment, limited only by the feature set of OpenStack Heat.


## How to deploy it

If you're an Open edX platform administrator, there's an easy way to deploy the
hastexo-xblock to a previously installed Open edX node (or cluster).  Just use
the `hastexo_xblock` role and accompanying `hastexo_xblock.yml` playbook
included in [hastexo's fork](https://github.com/hastexo/edx-configuration/tree/integration/cypress)
of `edx/configuration`.

From a checkout of the above branch, if running edX on a single node, run:

```
cd edx-configuration/playbooks

ansible-playbook hastexo_xblock.yml \
  -e hastexo_xblock_repo=https://github.com/hastexo/hastexo-xblock.git \
  -e hastexo_xblock_version=cypress \
  --tags edxapp_cfg
```

If you're deploying to Open edX on OpenStack, using, for instance, the
multi-node Heat template provided in the same branch of edx/configuration
above, then you should limit the run to just the app servers:

```
ansible-playbook -i openstack/inventory.py hastexo_xblock.yml \
  -e hastexo_xblock_repo=https://github.com/hastexo/hastexo-xblock.git \
  -e hastexo_xblock_version=cypress \
  --tags edxapp_cfg \
  --limit app_servers
```

Note that currently, the hastexo_xblock role depends on modifications to
edx/configuration that have yet to be accepted upstream, so it must be run from
the above branch.


## How to use it

As a course author, it is very simple to use the XBlock (provided it is
installed in your Open edX platform as described above).  To start with, upload
a Heat template to the content store, and make a note of its static asset file
name.

The template itself has a few constraints, as follows:

1.  An SSH key pair must be generated dynamically by the template, and the
    private key must be saved.  For instance:

```
  training_key:
    type: OS::Nova::KeyPair
    properties:
      name: { get_param: 'OS::stack_name' }
      save_private_key: true
```

2. It must create an instance that is publically accessible on the internet,
   via `floating_ip_address`.

3. It must provide the above two items as outputs, with the following names:

```
outputs:
  public_ip:
    description: Floating IP address of deploy in public network
    value: { get_attr: [ deploy_floating_ip, floating_ip_address ] }
  private_key:
    description: Training private key
    value: { get_attr: [ training_key, private_key ] }
```

Aside from the above constraints, you are free to do as you wish with your
training enviroment.  A sample template has been provided under
`heat-templates/hot/openstack-sample.yaml`.

To instruct the XBlock to create a stack for a student *and* to display a
terminal window where invoked, define the `hastexo` tag **once per section** in
your course content. (Doing so for more than one unit per section has undefined
behavior, as of the current version.)

As you can see below, in addition to the credentials to the public or private
OpenStack cloud of your choice, you'll need the static asset path to your Heat
template, and the name of the user that the XBlock will use to connect to the
environment via SSH:

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

In practice, this is what happens when students view course material with a tag
such as the above:

1. Whenever they navigate to a section with a 'hastexo' unit, even if it's not
   defined in the unit they're looking at, a Heat stack will be created (or
   resumed) for them, as defined by the uploaded Heat template.  It is unique
   per student and per course run (i.e., if the same tag appears on a different
   course, or different run of the same course, the student will get a
   different stack).

2. If the student doesn't navigate to the `hastexo` unit in that section in 2
   minutes, their stack will be suspended.

3. When the student finally gets to the `hastexo` unit, if the stack is
   suspended it will be resumed, and they will be connected automatically and
   securely, with no username, password, or host prompts, to their personal lab
   environment.  All this happens transparently, in the browser.

4. The student can then work at their leisure on their environment.  However, when they
   close the browser tab or window where the `hastexo` unit is displayed (maybe
   by putting their computers to sleep, or just closing the browser), a timer
   is started: if they don't reopen it within two minutes, their stack will be
   suspended, thus spending no further resources while it stays that way.

5. If after a couple of hours or days the student comes back to the above
   section to finish the exercise, their stack is resumed automatically.  They
   are subsequently connected, just as transparently as before, to the same
   training enviroment they were working with before, **at the state they left
   it in**.


## License

This XBlock is licensed under the Affero GPL; see [`LICENSE`](LICENSE)
for details.
