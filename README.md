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
- [Examples](#examples)
  - [P-states](#p-states)
  - [C-states](#c-states)
  - [CPU hotplug](#cpu-hotplug)
  - [CPU topology](#cpu-topology)
- [FAQ](#faq)

# Introduction

Pepc stands for "Power, Energy, and Performance Configurator". This is a command-line tool for
configuring CPU power management features.

**IMPORTANT**: this is tool is for debug and research purposes only. It requires root permissions,
and must only be used in an isolated lab environment, not in production.

## Context

There are many Linux tools for configuring power management in Linux, and this sub-section tries to
explain why we created yet another one.

We are doing a lot of work related to power and performance, such as measuring C-states latency
using [wult](https://github.com/intel/wult), running various workloads and collecting power and
performance statistics using [stats-collect](https://github.com/intel/stats-collect). We often
need to configure various power and performance aspects of the system, for example, enable or
disable C-states, limit CPU or uncore frequency, tweak hardware features like C1 demotion, and
so on.

Before 'pepc' was created, we had to use many different tools, such as 'cpupower' or 'lscpu',
remember sysfs paths for various knobs, such a path to disable a C-state. This was difficult
and error-prone. It was also not flexible enough for us. For example, disabling C1 only for one CPU
module was a difficult task, because one has to first figure out what are the CPU numbers in that
module, and then disable C1 on every CPU. And finally, many hardware features like C1 demotion
requires knowledge of the MSR register and the bit number to toggle. The 'wrmsr' and 'rdmsr' are
helpful tools, but they were not easy enough for us to use on a regular basis.

We created 'pepc' to make power and performance configuration tasks easier. With pepc, we do not
have to remember sysfs paths and platform-specific MSR (Model Specific Register) numbers. The tool
is flexible, supports many CPU models, well-structured, and also provides Python API for other
python projects to use.

# Authors and contributors

* Artem Bityutskiy <dedekind1@gmail.com> - original author, project maintainer.
* Antti Laakso <antti.laakso@linux.intel.com> - contributor, project maintainer.
* Niklas Neronin <niklas.neronin@intel.com> - contributor, project maintainer.
* Tero Kristo <tero.kristo@intel.com> - contributor.
* Adam Hawley <adam.james.hawley@intel.com> - contributor.
* Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com> - contributor.
* Juha Haapakorpi <juha.haapakorpi@intel.com> - contributor.

# What is supported

Pepc supports discovering and configuring the following features.
* C-states: [documentation](docs/pepc-cstates.rst)
* P-states: [documentation](docs/pepc-pstates.rst)
* Power: [documentation](docs/pepc-power.rst)
* CPU onlining and offlining: [documentation](docs/pepc-cpu-hotplug.rst)
* ASPM: [documentation](docs/pepc-aspm.rst)
* CPU topology: [documentation](docs/pepc-topology.rst)

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

This will create the 'pepc.standalone' file, which you can rename and copy anywhere. It will work
as a standalone program.

## Tab completions

'Pepc' has tab completions support, but this will only work if you have certain environment
variables defined. The following command will do it:

```
eval "$(register-python-argcomplete pepc)"
```

You can put this line to your '.bashrc' file in order to have 'pepc' tab completions enabled by
default.

# Examples

## P-states

### Get all the genearlly interesting P-states information:

```
$ pepc pstates info
Source: Linux sysfs file-system
 - Min. CPU frequency: '1.2GHz' for CPUs 0-87 (all CPUs)
 - Max. CPU frequency: '3.6GHz' for CPUs 0-87 (all CPUs)
 - Min. supported CPU frequency: '1.2GHz' for CPUs 0-87 (all CPUs)
 - Max. supported CPU frequency: '3.6GHz' for CPUs 0-87 (all CPUs)
 - Base CPU frequency: '2.2GHz' for CPUs 0-87 (all CPUs)
 - Turbo: 'on' for CPUs 0-87 (all CPUs)
 - Min. uncore frequency: '1.2GHz' for CPUs 0-87 (all CPUs)
 - Max. uncore frequency: '2.8GHz' for CPUs 0-87 (all CPUs)
 - Min. supported uncore frequency: '1.2GHz' for CPUs 0-87 (all CPUs)
 - Max. supported uncore frequency: '2.8GHz' for CPUs 0-87 (all CPUs)
 - EPB: '7' for CPUs 0-87 (all CPUs)
 - CPU frequency driver: intel_pstate
 - Operation mode of 'intel_pstate' driver: 'passive' for CPUs 0-87 (all CPUs)
 - CPU frequency governor: 'schedutil' for CPUs 0-87 (all CPUs)
 - Available CPU frequency governors: conservative, ondemand, userspace, powersave, performance, schedutil
Source: Model Specific Register (MSR)
 - Bus clock speed: '100MHz' for CPUs 0-87 (all CPUs)
 - Min. CPU operating frequency: '800MHz' for CPUs 0-87 (all CPUs)
 - Max. CPU efficiency frequency: '1.2GHz' for CPUs 0-87 (all CPUs)
 - Max. CPU turbo frequency: '3.6GHz' for CPUs 0-87 (all CPUs)
 - EPB: '7' for CPUs 0-87 (all CPUs)
```

### Get base CPU frequency and CPU frequency driver name

```
$ pepc pstates info --base-freq --driver
Base CPU frequency: '2.2GHz' for CPUs 0-87 (all CPUs)
CPU frequency driver: intel_pstate
```

### Set min. and max. CPU frequency

Limit CPU frequency rearrange to [1.5GHz, 2GHz] for all CPUs.

```
$ pepc pstates config --min-freq 1.5GHz --max-freq 2GHz
Min. CPU frequency: set to '1.5GHz' for CPUs 0-87 (all CPUs)
Max. CPU frequency: set to '2GHz' for CPUs 0-87 (all CPUs)
```

Verify it.

```
$ pepc pstates info --min-freq --max-freq
Min. CPU frequency: '1.5GHz' for CPUs 0-87 (all CPUs)
Max. CPU frequency: '2GHz' for CPUs 0-87 (all CPUs)
```

Lock CPU frequency to base frequency (HFM) for all CPUs in cores 0 and 4 of package 1.

```
pepc pstates config --min-freq base --max-freq base --packages 1 --cores 0,4
Min. CPU frequency: set to '2.2GHz' for CPUs 1,9,45,53
Max. CPU frequency: set to '2.2GHz' for CPUs 1,9,45,53
```

Verify it.

```
$ pepc pstates info --min-freq --max-freq
Min. CPU frequency: '1.5GHz' for CPUs 0,2-8,10-44,46-52,54-87
Min. CPU frequency: '2.2GHz' for CPUs 1,9,45,53
Max. CPU frequency: '2GHz' for CPUs 0,2-8,10-44,46-52,54-87
Max. CPU frequency: '2.2GHz' for CPUs 1,9,45,53
```

Unlock CPU frequency on all CPUs.

```
$ pepc pstates config --min-freq min --max-freq max
Min. CPU frequency: set to '1.2GHz' for CPUs 0-87 (all CPUs)
Max. CPU frequency: set to '3.6GHz' for CPUs 0-87 (all CPUs)
```

Verify it.

```
$ pepc pstates info --min-freq --max-freq
Min. CPU frequency: '1.2GHz' for CPUs 0-87 (all CPUs)
Max. CPU frequency: '3.6GHz' for CPUs 0-87 (all CPUs)
```

### Change Linux CPU frequency governor

First, get the name of current governor and list of supported governors.

```
$ pepc pstates info --governor --governors
CPU frequency governor: 'schedutil' for CPUs 0-87 (all CPUs)
Available CPU frequency governors: conservative, ondemand, userspace, powersave, performance, schedutil
```

Switch to the "performance" governor.

```
$ pepc pstates config --governor performance
CPU frequency governor: set to 'performance' for CPUs 0-87 (all CPUs)
```

Verify it.

```
$ pepc pstates info --governor
CPU frequency governor: 'performance' for CPUs 0-87 (all CPUs)
```

## C-states

### Get all the genearlly interesting C-states information

```
$ pepc cstates info
Source: Linux sysfs file-system
 - POLL: 'on' for CPUs 0-87 (all CPUs)
    - description: CPUIDLE CORE POLL IDLE
    - expected latency: 0 us
    - target residency: 0 us
 - C1: 'on' for CPUs 0-87 (all CPUs)
    - description: MWAIT 0x00
    - expected latency: 2 us
    - target residency: 2 us
 - C1E: 'on' for CPUs 0-87 (all CPUs)
    - description: MWAIT 0x01
    - expected latency: 10 us
    - target residency: 20 us
 - C3: 'off' for CPUs 0-87 (all CPUs)
    - description: MWAIT 0x10
    - expected latency: 40 us
    - target residency: 100 us
 - C6: 'on' for CPUs 0-87 (all CPUs)
    - description: MWAIT 0x20
    - expected latency: 133 us
    - target residency: 400 us
Source: Model Specific Register (MSR)
 - Package C-state limit: 'PC6' for CPUs 0-87 (all CPUs)
 - Package C-state limit lock: 'on' for CPUs 0-87 (all CPUs)
 - Available package C-state limits: PC0, PC2, PC3, PC6, unlimited
 - C1 demotion: 'off' for CPUs 0-87 (all CPUs)
 - C1 undemotion: 'off' for CPUs 0-87 (all CPUs)
 - C1E autopromote: 'off' for CPUs 0-87 (all CPUs)
 - C-state prewake: 'on' for CPUs 0-87 (all CPUs)
Source: Linux sysfs file-system
 - Idle driver: intel_idle
 - Idle governor: 'menu' for CPUs 0-87 (all CPUs)
 - Available idle governors: menu
```

### Get information about C1, C1E autopromote, and C1 demotion

```
$ pepc cstates info --cstates C1 --c1e-autopromote --c1-demotion
C1: 'on' for CPUs 0-87 (all CPUs)
 - description: MWAIT 0x00
 - expected latency: 2 us
 - target residency: 2 us
C1E autopromote: 'off' for CPUs 0-87 (all CPUs)
C1 demotion: 'off' for CPUs 0-87 (all CPUs)
```

### Toggle C-states

Disable all C-states but POLL on all CPUs.

```
$ pepc cstates config --disable all --enable POLL
POLL: set to 'off' for CPUs 0-87 (all CPUs)
C1: set to 'off' for CPUs 0-87 (all CPUs)
C1E: set to 'off' for CPUs 0-87 (all CPUs)
C3: set to 'off' for CPUs 0-87 (all CPUs)
C6: set to 'off' for CPUs 0-87 (all CPUs)
POLL: set to 'on' for CPUs 0-87 (all CPUs)
```

Enable all C-states on all CPUs.

```
$ pepc cstates config --enable all
POLL: set to 'on' for CPUs 0-87 (all CPUs)
C1: set to 'on' for CPUs 0-87 (all CPUs)
C1E: set to 'on' for CPUs 0-87 (all CPUs)
C3: set to 'on' for CPUs 0-87 (all CPUs)
C6: set to 'on' for CPUs 0-87 (all CPUs)
```

Disable C1E and C6 on package 1.

```
$ pepc cstates config --disable C1E,C6 --packages 1
C1E: set to 'off' for CPUs 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47,49,51,53,55,57,59,61,63,65,67,69,71,73,75,77,79,81,83,85,87 (package 1)
C6: set to 'off' for CPUs 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47,49,51,53,55,57,59,61,63,65,67,69,71,73,75,77,79,81,83,85,87 (package 1)
```

### Configure package C-state limit

Get package C-state limit information.

```
$ pepc cstates info --pkg-cstate-limit
Package C-state limit: 'PC6' for CPUs 0-87 (all CPUs)
Package C-state limit lock: 'off' for CPUs 0-87 (all CPUs)
Available package C-state limits: PC0, PC2, PC3, PC6, unlimited
```

Since package C-state limit MSR is not locked, we can modify the limit. Set the deepest
allowed package C-state to PC0 on all packages.

```
$ pepc cstates config --pkg-cstate-limit PC0 --packages all
Package C-state limit set to 'PC0' for CPUs 0-87 (all CPUs)
```

## CPU hotplug

### Online/offline certain CPUs

First, check the current online/offline situation.

```
$ pepc cpu-hotplug info
The following CPUs are online: 0-87
No offline CPUs
```

Offline CPUs 5,6,7,8 and CPU 87.

```
$ pepc cpu-hotplug offline --cpus 5-8,87
Offlining CPU5
Offlining CPU6
Offlining CPU7
Offlining CPU8
Offlining CPU87
```

### Online all CPUs

```
$ pepc cpu-hotplug online --cpus all
Onlining CPU5
Onlining CPU6
Onlining CPU7
Onlining CPU8
Onlining CPU87
```

### Disable hyperthreads by offlining core siblings

Core siblings are CPUs withing one core. On Intel chips, there are the hyperthreads.
If a system has two CPUs (execution units, hyperthreads) per core, then their core
sibling indices are 0 and 1. To disable hyperthreads, offline all core siblings with
index 1.


```
$ pepc cpu-hotplug offline --cpus all --core-siblings 1
```

Hint: use 'pepc topology info --columns core,cpu' to figure out the relation between
core and CPU numbers.

### Offline package 1

On a multi-socket systems there are multiple CPU packages. You can offline all CPUs
of a package to effectively "disable" it. Here is how to do it for package 1.

```
$ pepc cpu-hotplug offline --packages 1
```

## CPU topolgy

### Print the topology table

```
$ pepc topology info
CPU    Core    Node    Package
  0       0       0          0
  1       0       1          1
  2       1       0          0
  3       1       1          1

... snip ...

 85      27       1          1
 86      28       0          0
 87      28       1          1
```

The table gives an idea about how CPU, core, NUMA node and package numbers are related
to each other.

# FAQ

## What to do if my platform is not supported?

Some 'pepc' features (e.g., '--pkg-cstate-limit') are implemented only for certain Intel platforms.
This does not necessarily mean that the feature is not supported by other platforms, it only means
that we verified it on a limited amount of platforms. Just to be on a safe side, we refuse changing
the underlying MSR registers on platforms we did not verify.

If 'pepc' fails with a message like "this feature is not supported on this platform" for you, feel
free to contact the authors with a request. Very often it ends up with just adding a CPU ID to the
list of supported platforms, and may be you can do it yourself and submit a patch/pull request.
