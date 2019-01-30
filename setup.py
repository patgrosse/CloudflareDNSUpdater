#!/usr/bin/env python

from setuptools import setup

setup(name="CloudFlareDNSUpdater",
      version="0.1",
      description="Update IPv4 or IPv6 record according to external address of current machine",
      author="Patrick Grosse",
      author_email="patrick.pgrosse@gmail.com",
      packages=["cfdnsupdater"],
      scripts=["bin/updatecfdns"],
      install_requires=["CloudFlare==2.1.0"]
      )
