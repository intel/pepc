<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Pepc User Guide: CPU Hotplug

- Author: Artem Bityutskiy <dedekind1@gmail.com>

## Table of Contents

- [Introduction](#introduction)
- [Examples](#examples)
  - [Offline Certain CPUs](#offline-certain-cpus)
  - [Online All CPUs](#online-all-cpus)
  - [Disable Hyperthreads](#disable-hyperthreads)
  - [Offline a Package](#offline-a-package)

## Introduction

The `pepc cpu-hotplug` command groups operations related to CPU hotplug functionality in Linux.
Today, this includes onlining and offlining CPUs.

What does offlining a CPU do in Linux? At a high level, it migrates all tasks and interrupts
away from the target CPU, removes the CPU from the scheduler's list of available CPUs, and then
puts the CPU into the lowest C-state. The CPU ends up running a forever loop, where it requests
the deepest C-state (e.g., C6 on Intel Xeon platforms). In the ideal case, it never wakes up
again. But if there are spurious wake-ups, it simply requests the deepest C-state again. The
Linux kernel uses the CPU reset vector to online the CPU again.

Keep in mind that offlining CPUs on Intel platforms is not the same as disabling cores in BIOS.
Unlike disabled cores, offline CPUs still consume some hardware, firmware, and OS resources.

## Examples

### Offline Certain CPUs

First, check the current online/offline situation.

```bash
$ pepc cpu-hotplug info
The following CPUs are online: 0-87
No offline CPUs
```

Offline CPUs 5,6,7,8 and CPU 87.

```bash
$ pepc cpu-hotplug offline --cpus 5-8,87
Offlining CPU5
Offlining CPU6
Offlining CPU7
Offlining CPU8
Offlining CPU87
```

### Online All CPUs

```bash
$ pepc cpu-hotplug online --cpus all
Onlining CPU5
Onlining CPU6
Onlining CPU7
Onlining CPU8
Onlining CPU87
```

### Disable Hyperthreads

Core siblings are CPUs within one core. On Intel chips, these are the hyperthreads.
If a system has two CPUs per core, then their core sibling indices are 0 and 1. To disable
hyperthreads, offline all core siblings with index 1. This goes through each core and offlines
the second CPU (hyperthread) of that core (index 0 is the first CPU of the core, index 1 is the
second CPU of the core).

```bash
$ pepc cpu-hotplug offline --cpus all --core-siblings 1
```

**Hint**: use 'pepc topology info --columns core,cpu' to figure out the relation between core and
CPU numbers.

### Offline a Package

On multi-socket systems there are multiple CPU packages. You can offline all CPUs of a package
to effectively "disable" it. Here is how to do it for package 1.

```bash
$ pepc cpu-hotplug offline --packages 1
```
