#!/usr/bin/python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""The standard python packaging script."""

import re
from setuptools import setup, find_packages

def get_version(filename):
    """Fetch the project version number."""

    with open(filename, "r", encoding="utf-8") as fobj:
        for line in fobj:
            matchobj = re.match(r'^_VERSION = "(\d+.\d+.\d+)"$', line)
            if matchobj:
                return matchobj.group(1)
    return None

setup(
    name="pepc",
    description="""Power, Energy, and Performance configuration tool""",
    author="Artem Bityutskiy",
    author_email="artem.bityutskiy@linux.intel.com",
    python_requires=">=3.7",
    version=get_version("pepctool/_Pepc.py"),
    scripts=["pepc"],
    packages=find_packages(exclude=["test*"]),
    long_description="""A tool configuring various power and performance aspects of a Linux
                        system.""",
    install_requires=["paramiko", "pyyaml", "colorama", "argcomplete"],
    classifiers=[
        "Intended Audience :: Developers",
        "Topic :: System :: Hardware",
        "Topic :: System :: Operating System Kernels :: Linux",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3 :: Only",
        "Development Status :: 4 - Beta",
    ],
)
