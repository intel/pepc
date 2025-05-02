<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->
- [Introduction](#introduction)
  - [Context](#context)
- [Authors](#authors-and-contributors)
- [What is supported](#what-is-supported)
- [Installation](#installation)
  - [Dependencies](#dependencies)
    - [Fedora](#fedora-1)
    - [Ubuntu](#ubuntu)
  - [Requirements](#requirements)
  - [Using uv](#using-uv)
  - [Using pip](#using-pip)
  - [Fedora](#fedora)
  - [CentOS 9 Stream](#centos-9-stream)
  - [Standalone version](#standalone-version)
  - [Tab completions](#tab-completions)
- [Examples](#examples)
  - [P-states](#p-states)
  - [C-states](#c-states)
  - [PM QoS](#pm-qos)
  - [Power](#power)
  - [ASPM](#aspm)
  - [CPU hotplug](#cpu-hotplug)
  - [CPU topology](#cpu-topology)
- [FAQ](#faq)

# Introduction

Pepc, short for "Power, Energy, and Performance Configurator," is a command-line tool designed for
managing and optimizing CPU power management features.

**IMPORTANT**: This tool is intended for debugging and research purposes only. It requires root
permissions and should only be used in a lab environment, not in production.

## Context

There are numerous Linux tools for power management configuration. This section explains why we
created another one.

We work on power and performance, including measuring C-state latencies using
[wult](https://github.com/intel/wult) and collecting power and performance statistics using
[stats-collect](https://github.com/intel/stats-collect). We frequently configure power and
performance  settings, such as enabling/disabling C-states, limiting CPU/uncore frequency,
or tweaking features like C1 demotion, among others.

Before pepc, we relied on multiple tools like cpupower and lscpu, and memorized sysfs paths for
various settings, such as disabling a C-state. This approach was cumbersome and error-prone. It
lacked flexibility; for instance, disabling C1 for a single CPU module required identifying the
CPU numbers in that module and disabling C1 for each CPU individually. Additionally, configuring
hardware features like C1 demotion required knowledge of MSR registers and specific bit toggles.
While tools like wrmsr and rdmsr were useful, they were not user-friendly for frequent use.

Pepc simplifies power and performance configuration by eliminating the need to remember sysfs paths
and platform-specific MSR numbers. It is flexible, supports various CPU models, well-structured,
and offers a Python API for integration with other Python projects.

# Authors and contributors

* Artem Bityutskiy <dedekind1@gmail.com> - original author, project maintainer.
* Antti Laakso <antti.laakso@linux.intel.com> - contributor, project maintainer.
* Niklas Neronin <niklas.neronin@intel.com> - contributor.
* Adam Hawley <adam.james.hawley@intel.com> - contributor.
* Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com> - contributor.
* Juha Haapakorpi <juha.haapakorpi@intel.com> - contributor.
* Tero Kristo <tero.kristo@gmail.com>> - contributor.

# What is supported

Pepc supports discovering and configuring the following features.
* C-states: [documentation](docs/pepc-cstates.rst)
* P-states: [documentation](docs/pepc-pstates.rst)
* PM QoS: [documentation](docs/pepc-pmqos.rst)
* Power: [documentation](docs/pepc-power.rst)
* CPU onlining and offlining: [documentation](docs/pepc-cpu-hotplug.rst)
* ASPM: [documentation](docs/pepc-aspm.rst)
* CPU topology: [documentation](docs/pepc-topology.rst)
* TPMI: [documentation](docs/pepc-tpmi.rst)

Some features are hardware-agnostic, while others depend on specific hardware capabilities.

# Installation

## Dependencies

Pepc requires certain system tools and libraries. Below are the installation instructions.

### Fedora

```
sudo dnf install -y rsync util-linux procps-ng
```

### Ubuntu

```
sudo apt install -y rsync util-linux procps
```

## Requirements

* Pepc requires Python 3.9 or newer.
* Run pepc as a superuser (e.g., using "sudo").
* Many options need access to MSRs (Model Specific Registers), requiring the "msr" kernel driver
  Ensure the "msr" kernel driver is available, as some Linux distributions may disable it by default.

## Using uv

Uv is a modern Python project and package management tool. Install it on your system. Many Linux
distributions provide a package for it. Also install git. For example, in Fedora, run:

```
sudo dnf install uv git
```

Install pepc by running the following command.

```
uv tool install git+https://github.com/intel/pepc.git@release
```

uv installs projects to '$HOME/.local'. Ensure '$HOME/.local/bin' is in your 'PATH'.

```
$ which pepc
~/.local/bin/pepc
```

If you installed pepc as root and plan to use pepc as root, no additional steps are required.

### sudo complication

Unfortunately, running pepc with sudo works only when you provide the full path to the executable.

```
sudo ~/.local/bin/pepc --version
1.5.32
```

Using only the command name causes an error.

```
sudo pepc
sudo: pepc: command not found
```

To overcome this, create an alias as shown below and add it to your `$HOME/.bashrc` file:

```
alias pepc="sudo $HOME/.local/bin/pepc"
```
You can now run `pepc` directly. For example:

```
pepc pstates info
[sudo] password for user: 
Source: Linux sysfs file-system
 - Turbo: on
 - Min. CPU frequency: 800.00MHz for all CPUs
... snip ...
```

## Using pip

Install pip on your system. Most modern Linux distributions include a package for pip installation.
Also install git. For example, in Fedora, run

```
dnf install python-pip git
```

Install pepc into a python virtual enviroment using the following commands.

```
python3 -m venv ~/.pmtools
~/.pmtools/bin/pip3 install git+https://github.com/intel/pepc.git@release
```

Ensure that '$HOME/.pmtools/bin' is in your 'PATH'. Verify this as follows.

```
$ which pepc
~/.pmtools/bin/pepc
```

If you installed pepc as root and plan to use pepc as root, no additional steps are required.

### sudo complication

Similar to the "using uv" case, create an alias and add it to your `$HOME/.bashrc` file as shown below:

```
alias pepc="sudo VIRTUAL_ENV=$HOME/.pmtools $HOME/.pmtools/bin/pepc"
```

## Fedora

Pepc is available in Fedora starting from version 38. However, Fedora packages may not provide the
latest version. To install the latest release, use the "uv" or "pip" methods.

To install pepc, run:

```
sudo dnf install pepc
```

Fedora packages are maintained by Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com>.

## CentOS 9 Stream
Pepc is available for CentOS 8 Stream via the EPEL repository. Note that EPEL packages may not
always provide the latest version. To get the latest release, consider using the "uv" or "pip"
installation methods.

To add EPEL and install Pepc, follow these steps:

```
sudo dnf install epel-release
sudo dnf install pepc
```

Epel packages are maintained by Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com>.

## Standalone version
To create a standalone version of pepc, ensure your Python version is greater than 3.8.
Run the following command, which should print "Good" if the version is compatible:

```
/usr/bin/python3 -c 'import sys; ver=sys.version_info; \
print("Good") if ver.major > 2 and ver.minor > 8 else print("Bad")'
```

Create the standalone version of pepc.

```
git clone https://github.com/intel/pepc.git --branch release pepc
cd pepc
echo '#!/usr/bin/python3' > pepc.standalone
git archive --format zip HEAD >> pepc.standalone
chmod ug+x pepc.standalone
```
This creates the 'pepc.standalone' file, which you can rename and copy anywhere for standalone use.

## Tab completions

Pepc supports tab completions, but it requires specific environment variables to be set. Use the
following:

```
eval "$(register-python-argcomplete pepc)"
```

Add this line to '$HOME/.bashrc' file to enable tab completion by default.

# Examples

## P-states

### Get all the generally interesting P-states information:

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

### Get all the generally interesting C-states information

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

## PM QoS

### Get all the PM QoS information

```
$ pepc pmqos info
Source: Linux sysfs file-system
 - Linux per-CPU PM QoS latency limit: 0 (no limit) for all CPUs
Source: Linux character device node
 - Linux global PM QoS latency limit: 2000s
 ```

### Set the per-CPU latency limits

Set latency limit to 100us for all CPUs in package 1, and also for CPU 0.

```
$ pepc pmqos config --latency-limit 100us --package 1 --cpus 0
Linux per-CPU PM QoS latency limit: set to 100us for CPUs 0,56-111,168-223
```

Verify it.

```
$ pepc pmqos info
Source: Linux sysfs file-system
 - Linux per-CPU PM QoS latency limit: 100us for CPUs 0,56-111,168-223
 - Linux per-CPU PM QoS latency limit: 0 (no limit) for CPUs 1-55,112-167
Source: Linux character device node
 - Linux global PM QoS latency limit: 2000s
```

## Power

### Get all the generally interesting power information

```
$ pepc power info
Source: Model Specific Register (MSR)
 - TDP: 83W for all CPUs
 - RAPL PPL1: 83W for all CPUs
 - RAPL PPL1: 'on' for all CPUs
 - RAPL PPL1 clamping: 'on' for all CPUs
 - RAPL PPL1 time window: 1s for all CPUs
 - RAPL PPL2: 99.625W for all CPUs
 - RAPL PPL2: 'on' for all CPUs
 - RAPL PPL2 clamping: 'on' for all CPUs
 - RAPL PPL2 time window: 1s for all CPUs
```

## ASPM

### Get all the generally interesting ASPM information

```
$ pepc aspm info
ASPM policy: default
Available policies: default, performance, powersave, powersupersave
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

## CPU topology

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

Some pepc features (e.g., --pkg-cstate-limit) are implemented only for certain Intel platforms.
This does not necessarily mean that the feature is not supported by other platforms, it only means
that we verified it on a limited amount of platforms. Just to be on a safe side, we refuse changing
the underlying MSR registers on platforms we did not verify.

If pepc fails with a message like "this feature is not supported on this platform" for you, feel
free to contact the authors with a request. Very often it ends up with just adding a CPU ID to the
list of supported platforms, and may be you can do it yourself and submit a patch/pull request.
