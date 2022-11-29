<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->
- [Introduction](#introduction)
  - [Context](#tool-context)
- [Authors](#authors-and-contributors)
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
* Niklas Neronin <niklas.neronin@intel.com> - contributor.
* Adam Hawley <adam.james.hawley@intel.com> - contributor.
* Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com> - contributor.
* Juha Haapakorpi <juha.haapakorpi@intel.com> - contributor.

# What is supported

Pepc supports the following features:
* C-states: discovering and configuring.
* P-states: discovering and configuring.
* CPU hotplug: onlining and offlining CPUs.
* ASPM: discovering and configuring.
* CPU topology: discovering.

Please, refer to the [man page](docs/pepc-man.rst) for details.

Some of the features are hardware-independent, but some are hardware-specific.

# Installation

## Fedora

'Pepc' is part of Fedora starting from Fedora 35. To install 'pepc', run

```
sudo dnf install pepc
```

Fedora packages are maintained by Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com>.

In case of Fedora 34 or older Fedora, use the 'pip' installation method. But install
the dependencies by running

```
sudo dnf install -y rsync openssl-devel util-linux procps-ng
sudo dnf install -y python3-colorama python3-paramiko python3-argcomplete
```

## CentOS 9 Stream

'Pepc' is available for CentOS 9 Stream via the 'epel' repository. Here is how to add 'epel' and
install 'pepc'.

```
sudo dnf install epel-release
sudo dnf install pepc
```

Epel packages are maintained by Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com>.

## CentOS 8 Stream

To install 'pepc' in CentOS stream, you can use the
["copr"](https://copr.fedorainfracloud.org/coprs/aekoroglu/c8s-py39/) repository
maintained by Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com>.

Run the following commands.

```
sudo dnf copr enable aekoroglu/c8s-py39 centos-stream-8-x86_64
sudo dnf install pepc
```

## Ubuntu and Debian

We do not provide Ubuntu/Debian packages, so you'll need to use the 'pip' installation method.
Install the following dependencies, though.

```
sudo apt install -y rsync libssl-dev util-linux procps python3 git
sudo apt install -y python3-pip python3-colorama python3-paramiko python3-argcomplete
```

## Installing with 'pip'

Run the following command:

```
sudo pip3 install --upgrade git+https://github.com/intel/pepc.git@release
```

This command will download 'pepc' from the 'release' branch of the git repository and
install it to the system.

The other way of doing this is by first cloning the git repository and running

```
git clone https://github.com/intel/pepc.git --branch release pepc
cd pepc
pip3 install --upgrade .
```

Note, 'pepc' has to be run with superuser (root) privileges in many cases, and if you install it
with the '--user' option of 'pip3', it won't work "out of the box". This is why we do not recommend
using '--user'.

## Standalone version

You can also create a standalone version of this tool by cloning the repository and running a couple
of commands. Below is an example. You may want to adjust the '#!/usr/bin/python3' shebang in it.

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

This will create the 'pepc.stanalone' file, which you can rename and copy anywhere. It will work
as a standalone program.

## Tab completions

'Pepc' has tab completions support, but this will only work if you have certain environment
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
