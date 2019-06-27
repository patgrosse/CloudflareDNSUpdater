# CloudFlareDNSUpdater

Updates DNS entries with a machines current IP address (internal or external).

A tool useful in environments with dynamically changing IP addresses, eg. NAT, DHCP, IPv6 SLAAC or other non-statically configured systems.

Currently this tool is limited to using the CloudFlare API and thus is limited to CloudFlare nameservers.

## Features
* Updating IP once (eg. for cron jobs)
* Keeping track of IP changes via local netlink, [ipify](https://www.ipify.org/) or periodic interface checks
* Applicable for NAT environments with ipify
* Only update record at CloudFlare when required, minimizes requests to CloudFlare
* Robust concept aiming to run as a service/background task

## Requirements
Python version 3.7

pip modules: (can be installed with `setup.py`)
* `CloudFlare`
* `pyroute`

## Installation
As simple as:

`sudo python3 setup.py install`

## Overview

### Modes

#### Auto mode
The auto mode will keep track of IP changes and update a DNS entry accordingly.

#### Manual mode
The manual mode will trigger an update once (if required) and exit afterwards. Useful eg. for cron jobs.

### Tracker
Tracker are the modules that keep track of an IP address change or define the way an IP address is determined.

|                                | netlink                        | ipify                   | socket                  |
|--------------------------------|--------------------------------|-------------------------|-------------------------|
| **NAT support**                | no                             | yes                     | no                      |
| **External service contacted** | no                             | yes                     | no                      |
| **Update latency**             | instant                        | configurable in seconds | configurable in seconds |
| **Requirements**               | netlink API (Linux), `pyroute` | Internet connection     | -                       |


## Usage
Using `setup.py` the script `updatecfdns` will be installed in your PATH making it available on the command line.

### Auto mode
`updatecfdns --config <configfile> <--ipv4/--ipv6> --auto [--restart <seconds>] <tracker> [<tracker arguments>]`

### Manual mode
`updatecfdns --config <configfile> <--ipv4/--ipv6> --manual <tracker> [<tracker arguments>]`