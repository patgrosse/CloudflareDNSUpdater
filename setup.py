#!/usr/bin/env python3
from setuptools import setup

setup(name="CloudFlareDNSUpdater",
      version="0.5.0",
      description="Update IPv4 or IPv6 record according to external address of current machine",
      author="Patrick Grosse",
      author_email="patrick.pgrosse@gmail.com",
      packages=["cfdnsupdater"],
      scripts=["scripts/updatecfdns"],
      python_requires='>=3',
      install_requires=["CloudFlare==2.12.3", "pyroute2==0.7.3", "requests==2.31.0", "configparser==6.0.0"]
      )
