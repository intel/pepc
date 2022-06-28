<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->
- [Introduction](#introduction)
  - [Context](#tool-context)
- [Authors](#authors)
- [What is supported](#what-is-supported)
- [Installation](#installation)
  - [Dependencies](#dependencies)
  - [Using 'pip'](#using-pip)
  - [Standalone version](#standalone-version)
  - [Tab completions](#tab-completions)
- [FAQ](#faq)

# Introduction

Pepc stands for "Power, Energy, and Performance Configurator". This is a command-line tool for
configuring various Linux and Hardware power management features.

**IMPORTANT**: this is tool is for debug and research purposes only. It requires root permissions,
and must only be used in an isolated lab environment, not in production.

## Context

There are many Linux tools for configuring power management in Linux, and this sub-section tries to
explain why we created yet another one.

We develop, maintain, and use another project - [wult](https://github.com/intel/wult), and when we
measure a computer system with 'wult', we often need to configure it, for example, enable or disable
various C-states, limit CPU or uncore frequency, tweak hardware features like C1 demotion, and so on.

This required us to use many different tools and sysfs interfaces. It was difficult and error-prone,
until we created 'pepc', which supports everything we need for our research. For example, we can
limit C-states for a specific CPU, or core, or package with just one simple command. We can enable
or disable HW features without a need to remember MSR registers and bit numbers, and so on.

This project provides the tool and various modules that other projects like 'wult' can use. For
example, the 'CStates' module provides methods for discovering and manipulating C-states of a Linux
computer system.

# Authors and contributors

* Artem Bityutskiy <dedekind1@gmail.com> - original author, project maintainer.
* Antti Laakso <antti.laakso@linux.intel.com> - contributor, project maintainer.

# What is supported

Pepc supports the following features:
* C-states: discovering and configuring.
* P-states: discovering and configuring.
* CPU hotplug: onlining and offlining CPUs
* ASPM: discovering and configuring

Please, refer to the [man page](docs/pepc-man.rst) for details.

Some of the features are hardware-independent, but some are hardware-specific.

# Installation

## Dependencies

Before using or installing 'pepc', we recommend to install the following OS packages.

Fedora.

```
sudo dnf install -y rsync openssl-devel util-linux procps-ng
sudo dnf install -y python3-colorama python3-paramiko python3-argcomplete
```

Ubuntu.

```
sudo apt install -y rsync libssl-dev util-linux procps
sudo apt install -y python3 python3-colorama python3-paramiko python3-argcomplete
```

## Using 'pip'

The easiest way of installing 'pepc' is by using the 'pip' tool, and one way of doing this is by
running the following command:

```
pip3 install --user --upgrade git+https://github.com/intel/pepc.git@release
```

This command will download 'pepc' from the 'release' branch of the git repository, and install it to
the home directory. Note, the "release" branch contains more stable code. To install the latest code,
use the "master" branch instead.

The other way of doing this is by first cloning the git repository, checking out the 'release'
branch, and running the following command:

```
pip3 install --user --upgrade .
```

## Standalone version

You can create a standalone version of this tool by cloning the repository and running a couple of
commands. Below is an example. You may want to adjust the '#!/usr/bin/python3' shebang in it.

First of all, make sure the below command prints "Good". It verifies that your
'/usr/bin/python3' version is greater than 3.7:

```
/usr/bin/python3 -c 'import sys; ver=sys.version_info; \
print("Good") if ver.major>2 and ver.minor>6 else print("Bad")'
```

Create the standalone version of 'pepc'.

```
git clone https://github.com/intel/pepc.git --branch release pepc
cd pepc
echo '#!/usr/bin/python3' > pepc.standalone
git archive --format zip release >> pepc.standalone
chmod ug+x pepc.standalone
```

This will create the 'pepc.stanalone' file, which you can rename and copy to any other place, and it
will work as a standalone program.

## Tab completions

The 'pepc' tool has tab completions support, but this will only work if you have certain environment
variables defined. The following command will do it:

```
eval "$(register-python-argcomplete pepc)"
```

You can put this line to your '.bashrc' file in order to have 'pepc' tab completions enabled by
default.

# FAQ

## What to do if my platform is not supported?

Some 'pepc' features (e.g., '--pkg-cstate-limit') are implemented only for certain Intel platforms.
This does not necessarily mean that the feature is not supported by other platforms, it only means
that we verified it on a limited amount of platforms. Just to be on a safe side, we refuse changing
the underlying MSR registers on platforms we did not verify.

If 'pepc' fails with a message like "this feature is not supported on this platform" for you, feel
free to contact the authors with a request. Very often it ends up with just adding a CPU ID to the
list of supported platforms, and may be you can do it yourself and submit a patch/pull request.
