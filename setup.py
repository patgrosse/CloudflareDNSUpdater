#!/usr/bin/env python

import sys

from setuptools import setup

if sys.version_info < (3,):
    sys.exit('Sorry, Python < 3 is not supported')

setup(name="CloudFlareDNSUpdater",
      version="0.2",
      description="Update IPv4 or IPv6 record according to external address of current machine",
      author="Patrick Grosse",
      author_email="patrick.pgrosse@gmail.com",
      packages=["cfdnsupdater"],
      scripts=["scripts/updatecfdns"],
      python_requires='>=3.7',
      install_requires=["CloudFlare==2.3.0", "pyroute2==0.5.6", "requests==2.22.0"]
      )
