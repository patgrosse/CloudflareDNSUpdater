#!/usr/bin/env python3
from setuptools import setup

setup(name="CloudFlareDNSUpdater",
      version="0.4",
      description="Update IPv4 or IPv6 record according to external address of current machine",
      author="Patrick Grosse",
      author_email="patrick.pgrosse@gmail.com",
      packages=["cfdnsupdater"],
      scripts=["scripts/updatecfdns"],
      python_requires='>=3',
      install_requires=["CloudFlare==2.8.15", "pyroute2==0.6.5", "requests==2.26.0", "configparser==5.1.0"]
      )
