# CloudflareDNSUpdater

Updates DNS entries with a machines current IP address (internal or external).

A tool useful in environments with dynamically changing IP addresses, eg. NAT, DHCP, IPv6 SLAAC or other non-statically configured systems.

Currently this tool is limited to using the Cloudflare API and thus is limited to Cloudflare nameservers.

## Features
* Updating IP once (eg. for cron jobs)
* Keeping track of IP changes via local netlink, [ipify](https://www.ipify.org/) or periodic interface checks
* Applicable for NAT environments with ipify
* Only update record at Cloudflare when required, minimizes requests to Cloudflare
* Robust concept aiming to run as a service/background task

## Requirements
Python version 3.7

pip modules: (can be installed with `setup.py` or via `pip3 install -r requirements.txt`)
* `CloudFlare`
* `pyroute`
* more: see `requirements.txt`

## Installation
As simple as:

`sudo python3 setup.py install`

## Usage overview

If you use `setup.py` the script `updatecfdns` will be installed in your PATH making it available on the command line.

Usage on CLI:

`updatecfdns --config <configfile> <address type> <mode> <tracker> [<tracker arguments>]`

### Address type
This tool is capable of tracking IPv4 or IPv6 addresses.

* IPv4: `--ipv4` or `-4`
* IPv6: `--ipv6` or `-6`

### Modes

#### Auto mode
The auto mode will keep track of IP changes and update a DNS entry accordingly.

You can specify `--restart <seconds>` to automatically restart the tracker to increase robustness. Per default this is done after one day.

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

Trackers can have custom arguments, for more details, append `--help` to the command line.

### Config file
```
[api]
email = your.cloudflare.email@address.com
token = YoUrCL0udFlAR3APIt0KEn

[record]
zone = domain.com
name = subdomain.domain.com
```

## Docker

This project ships with a Dockerfile providing a basic Alpine Linux based container. Its usage is analogue to the standard CLI:

1. Build: `docker build . -t patgrosse/cfdnsupdater`
2. Use: `docker run --net=host -v <path/to/configfile.ini>:/config.ini patgrosse/cfdnsupdater --config /config.ini <arguments>`

Example:

`docker run --net=host -v /home/patrick/.secrets/dns_config.ini:/config.ini patgrosse/cfdnsupdater --config /config.ini -6 --auto netlink`

### Docker compose
See `docker-compose.yml` for an example.


## Notes

* You have to create the DNS entry at Cloudflare yourself, it is not created automatically by this tool.