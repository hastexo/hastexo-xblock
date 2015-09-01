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

## License

This XBlock is licensed under the Affero GPL; see [`LICENSE`](LICENSE)
for details.
