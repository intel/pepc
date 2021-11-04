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
  - [Using 'pip'](#installation-pip)
  - [Standalone version](#installation-pip)

# Introduction

Pepc stands for "Power, Energy, and Performance Configurator". This is a command-line tool for
configuring various Linux and Hardware power management features.

**IMPORTANT**: this is tool is for debug and research purposes only. It requres root permissions,
and must only be used in an isolated lab environment, not in production.

The project license is the 3-clause BSD license: https://opensource.org/licenses/BSD-3-Clause

## Context

There are many Linux tools for configuring power management in Linux, and this sub-section tries to
explain why we created yet another one.

We develop, maintain, and use another project - [wult](https://github.com/intel/wult), and when we
measure a computer system with 'wult', we often need to configure it, for example, enable or disable
varous C-states, limit CPU or uncore frequency, tweak hardware features like C1 demotion, and so on.

This required us to use many different tools and sysfs interfaces. It was difficult and error-prone,
until we created 'pepc', which supports everything we need for our research. For example, we can
limit C-states for a specific CPU, or core, or package with just one simple command. We can enable
or disable HW features without a need to remember MSR registers and bit numbers, and so on.

This project provides the tool and various modules that other projects like 'wult' can use. For
example, the 'CPUIdle' module provides methods for discovering and manipulating C-states of a Linux
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

## Using 'pip'

The easies way of installing 'pepc' is by using the 'pip' tool, and one way of doing this is by
running the following command:

```
pip install --user --upgrade git+https://github.com/intel/pepc.git@release
```

This command will download 'pepc' from the 'release' branch of the git repository, and install it to
the home direcory. Note, the "release" branch contains more stable code. To install the latest code,
use the "master" branch instead.

The other way of doing this is by first cloning the git repository, checking out the 'release'
branch, and running the following command:

```
pip install --user --upgrade .
```

## Standalone version

You can create a standalone version of this by cloning the repository and running a couple of
commands, here is an example:

```
git clone https://github.com/intel/pepc.git pepc
cd pepc
git checkout release
echo '#!/usr/bin/python3' > pepc.standalone
git archive --format zip HEAD >> pepc.standalone
chmod ug+x pepc.standalone
```

This will create the 'pepc.stanalone' file, which you can rename and copy to any other place, and it
will work as a standalone program.
