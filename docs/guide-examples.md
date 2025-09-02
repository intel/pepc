<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

Document author: Artem Bityutskiy <dedekind1@gmail.com>

- [Introduction](#introduction)
  - [P-states](#p-states)
  - [C-states](#c-states)
  - [PM QoS](#pm-qos)
  - [ASPM](#aspm)
  - [CPU hotplug](#cpu-hotplug)
  - [CPU topology](#cpu-topology)

# Introduction

This document demonstrates usage examples for the `pepc` tool, showcasing its various features.

**IMPORTANT**: This tool is intended for debugging and research purposes only. It requires root
permissions and should only be used in a lab environment, not in production.


## P-states

### Get all the generally interesting CPU P-states information:

```
$ pepc pstates info
Source: Linux sysfs file-system
 - Min. CPU frequency: '1.2GHz' for CPUs 0-87 (all CPUs)
 - Max. CPU frequency: '3.6GHz' for CPUs 0-87 (all CPUs)
 - Min. supported CPU frequency: '1.2GHz' for CPUs 0-87 (all CPUs)
 - Max. supported CPU frequency: '3.6GHz' for CPUs 0-87 (all CPUs)
 - Base CPU frequency: '2.2GHz' for CPUs 0-87 (all CPUs)
 - Turbo: 'on' for CPUs 0-87 (all CPUs)
 - EPB: '7' for CPUs 0-87 (all CPUs)
 - CPU frequency driver: intel_pstate
 - Operation mode of 'intel_pstate' driver: 'passive' for CPUs 0-87 (all CPUs)
 - CPU frequency governor: 'schedutil' for CPUs 0-87 (all CPUs)
 - Available CPU frequency governors: conservative, ondemand, userspace, powersave, performance, schedutil
Source: Model Specific Register (MSR)
 - Bus clock speed: '100MHz' for CPUs 0-87 (all CPUs)
 - Min. CPU operating frequency: '800MHz' for CPUs 0-87 (all CPUs)
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
