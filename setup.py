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
import os
from pathlib import Path
from setuptools import setup, find_packages

def get_version(filename):
    """Fetch the project version number."""

    with open(filename, "r", encoding="utf-8") as fobj:
        for line in fobj:
            matchobj = re.match(r'^_VERSION = "(\d+.\d+.\d+)"$', line)
            if matchobj:
                return matchobj.group(1)
    return None

def get_data_files(installdir, subdir, exclude=None):
    """
    When the task is to include all files in the 'subdir' directory to the package and install them
    under the 'installdir' directory, this function can be used to generate the list of files
    suitable for the 'data_files' setup parameter.
    """

    files_dict = {}
    for root, _, files in os.walk(subdir):
        for fname in files:
            fname = Path(f"{root}/{fname}")

            if exclude and str(fname) in exclude:
                continue

            key = str(Path(installdir) / fname.relative_to(subdir).parent)
            if key not in files_dict:
                files_dict[key] = []
            files_dict[key].append(str(fname))

    return list(files_dict.items())

setup(
    name="pepc",
    description="""Power, Energy, and Performance configuration tool""",
    author="Artem Bityutskiy",
    author_email="artem.bityutskiy@linux.intel.com",
    python_requires=">=3.8",
    version=get_version("pepctool/_Pepc.py"),
    scripts=["pepc"],
    packages=find_packages(exclude=["test*"]),
    data_files=get_data_files("share/man/man1", "docs/man1") + \
               get_data_files("share/pepc/tpmi", "tpmi"),
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
