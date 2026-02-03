<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Pepc User Guide: Uncore

- Author: Artem Bityutskiy \<dedekind1@gmail.com\>

## Table of Contents

- [Introduction](#introduction)
- [Uncore Frequency Control Mechanisms](#uncore-frequency-control-mechanisms)
- [New and Legacy Sysfs APIs](#new-and-legacy-sysfs-apis)
- [Uncore Frequency and Dies](#uncore-frequency-and-dies)
- [Examples](#examples)
  - [Get All Uncore Information](#get-all-uncore-information)
  - [Display Non-Compute Dies Details](#display-non-compute-dies-details)
  - [ELC Examples](#elc-examples)
- [CPU Hotplug](#cpu-hotplug)
  - [Examples](#examples-1)
- [CPU Topology](#cpu-topology)
- [PM QoS](#pm-qos)
  - [Examples](#examples-2)
- [TPMI](#tpmi)
- [ASPM](#aspm)
  - [Examples](#examples-3)

## Introduction

The `pepc uncore` command groups operations related to CPU uncore, for example reading or changing
uncore frequency limits.

"Uncore" is an informal term referring to the Intel CPU north complex blocks excluding the cores. For
example, it typically includes components like the last level cache (LLC), memory controller, and
north complex interconnects (e.g., between cores).

Some concepts related to uncore frequency scaling and the ELC (Efficiency Latency Control) feature
are explained in [Uncore ELC and Frequency Scaling](misc-uncore-elc.md).

## Uncore Frequency Control Mechanisms

The `pepc uncore` command supports two mechanisms for reading and changing uncore frequency
and ELC settings:
- 'sysfs': Uses the Linux sysfs file-system interface to read and change uncore frequency
  and ELC settings. Supports both legacy sysfs API and the new sysfs API.
- 'tpmi': Uses the TPMI (Topology Aware Register and PM Capsule Interface), bypassing Linux and
  talking directly to the hardware.

By default, `pepc uncore` uses the 'sysfs' mechanism, and if it is not available, it falls back to
the 'tpmi' mechanism. You can override this behavior by specifying the `--mechanism` option.

For detailed information about TPMI and low-level TPMI register operations, refer to the
[Pepc User Guide: TPMI](guide-tpmi.md).

## New and Legacy Sysfs APIs

The legacy sysfs API for uncore frequency scaling was used for older platforms, for example
Sky Lake and Cascade Lake Xeons. To be more precise, the legacy sysfs API is available on platforms
that support MSR 0x620 (MSR_UNCORE_RATIO_LIMIT). Example of a legacy sysfs path for package 0, die 1
is: '/sys/devices/system/cpu/intel_uncore_frequency/package_0_die_1'

For all platforms that support TPMI, the Linux uncore frequency driver provides the new sysfs API.
Example of a new sysfs path is: '/sys/devices/system/cpu/intel_uncore_frequency/uncore00'.

On Granite Rapids and Sierra Forest Xeon platforms, both new and legacy sysfs APIs are available.
However, the legacy sysfs API is very limited: it is effectively per-package, not per-die. So pepc
ignores the legacy sysfs API whenever the new sysfs API is available.

## Uncore Frequency and Dies

In pepc, a "die" is considered to be a unit of uncore frequency scaling. In other words, uncore
frequency is per-die.

Dies that include CPU cores are referred to as compute dies. Some dies do not include CPUs, but
still have uncore frequency scaling capability. For example, on Granite Rapids Xeon there are "I/O
dies" that include uncore blocks related to PCIe and CXL.

Typically client CPUs (e.g., Raptor Lake, Alder Lake) have a single compute die and no non-compute
dies. Many server CPUs (e.g., Ice Lake Xeon, Sapphire Rapids Xeon) have only a single compute die
and no non-compute dies as well. Some server CPUs (e.g., Cascade Lake-AP) have multiple compute dies
and no non-compute dies. Finally, newer server CPUs (e.g., Granite Rapids Xeon and Sierra Forest
Xeon) may have multiple compute dies and multiple non-compute dies.

Use `pepc topology info` to discover die topology on your system. For detailed information about
die topology, die enumeration methods, and die IDs, refer to the [Pepc User Guide:
Topology](guide-topology.md).

To get detailed information about dies and how they map to uncore frequency driver sysfs paths and TPMI UFS
feature addresses, use the `--dies-info` option of the `pepc uncore info` command.

## Examples

### Get All Uncore Information

Here is an example of running `pepc uncore info` on a Granite Rapids system.

```bash
$ pepc uncore info
Source: Linux sysfs file-system
 - Min. uncore frequency: 800.00MHz for all dies in all packages
 - Max. uncore frequency: 2.20GHz for dies 0-2 in package 0, dies 0-2 in package 1
 - Max. uncore frequency: 2.50GHz for dies 3,4 in package 0, dies 3,4 in package 1
 - Min. supported uncore frequency: 800.00MHz for all dies in all packages
 - Max. supported uncore frequency: 2.20GHz for dies 0-2 in package 0, dies 0-2 in package 1
 - Max. supported uncore frequency: 2.50GHz for dies 3,4 in package 0, dies 3,4 in package 1
 - ELC low zone min. uncore frequency: 1.20GHz for dies 0-2 in package 0, dies 0-2 in package 1
 - ELC low zone min. uncore frequency: 800.00MHz for dies 3,4 in package 0, dies 3,4 in package 1
 - ELC low threshold: 11% for all dies in all packages
 - ELC high threshold: 95% for all dies in all packages
 - ELC high threshold status: 'on' for all dies in all packages
```

Notice that compute dies (0-2) and I/O dies (3,4) have different maximum uncore frequencies.

The Raptor Lake client system has only one compute die and no non-compute dies, and it does not
support ELC.

```bash
$ pepc uncore info
Source: Linux sysfs file-system
 - Min. uncore frequency: 400.00MHz for all CPUs
 - Max. uncore frequency: 4.00GHz for all CPUs
 - Min. supported uncore frequency: 400.00MHz for all CPUs
 - Max. supported uncore frequency: 4.00GHz for all CPUs
```

### Display Non-Compute Dies Details

Here is an example of how to get detailed non-compute dies information on a Granite Rapids Xeon
system. The output is limited to package 1 only.

```bash
$ pepc uncore info --dies-info --packages 1
Package 1:
  - Die 0 (Compute):
    Linux UFS:
    - Path: /sys/devices/system/cpu/intel_uncore_frequency/uncore05
    TPMI UFS:
    - Address: 0000:80:03.1
    - Instance: 0
    - Cluster: 0
  - Die 1 (Compute):
    Linux UFS:
    - Path: /sys/devices/system/cpu/intel_uncore_frequency/uncore06
    TPMI UFS:
    - Address: 0000:80:03.1
    - Instance: 1
    - Cluster: 0
  - Die 2 (Compute):
    Linux UFS:
    - Path: /sys/devices/system/cpu/intel_uncore_frequency/uncore07
    TPMI UFS:
    - Address: 0000:80:03.1
    - Instance: 2
    - Cluster: 0
  - Die 3 (I/O):
    Linux UFS:
    - Path: /sys/devices/system/cpu/intel_uncore_frequency/uncore08
    TPMI UFS:
    - Address: 0000:80:03.1
    - Instance: 3
    - Cluster: 0
  - Die 4 (I/O):
    Linux UFS:
    - Path: /sys/devices/system/cpu/intel_uncore_frequency/uncore09
    TPMI UFS:
    - Address: 0000:80:03.1
    - Instance: 4
    - Cluster: 0
```

This gives detailed information about each die, including its type, sysfs path, TPMI address,
instance, and cluster.

On Granite Rapids Xeon there are 2 I/O dies per package. However, future Intel platforms may have
more die types, for example a memory die.

For information about die IDs and how they are assigned, see the [Pepc User Guide:
Topology](guide-topology.md).

### ELC Examples

For more examples related to uncore frequency scaling and ELC configuration, refer to
the [Uncore ELC and Frequency Scaling](misc-uncore-elc.md) article.

## CPU Hotplug

The `pepc cpu-hotplug` command groups operations related to CPU hotplug functionality in Linux.
Today, this includes onlining and offlining CPUs.

What does CPU offline do in Linux? At a high level, it migrates all tasks and interrupts away from the
target CPU, removes the CPU from the scheduler's list of available CPUs, and then puts the CPU into
the lowest C-state. The CPU ends up running a forever loop, where it requests the deepest C-state
(e.g., C6 on Intel Xeon platforms). In the ideal case, it never wakes up again. But if there are
spurious wake-ups, it simply requests the deepest C-state again. The Linux kernel uses the CPU reset
vector to online the CPU again.

Keep in mind that offlining CPUs on Intel platforms is not the same as disabling cores in BIOS.
Unlike disabled cores, offlined CPUs still consume some hardware, firmware and OS resources.

### Examples

**Offline certain CPUs**

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

**Online all CPUs**

```bash
$ pepc cpu-hotplug online --cpus all
Onlining CPU5
Onlining CPU6
Onlining CPU7
Onlining CPU8
Onlining CPU87
```

**Disable hyperthreads (core siblings)**

Core siblings are CPUs within one core. On Intel chips, these are the hyperthreads.
If a system has two CPUs per core, then their core sibling indices are 0 and 1. To disable
hyperthreads, offline all core siblings with index 1. This will go through every core, and offline
the second CPU (hyperthread) of that core (index 0 is the first CPU of the core, index 1 is the
second CPU of the core).

```bash
$ pepc cpu-hotplug offline --cpus all --core-siblings 1
```

**Hint**: use 'pepc topology info --columns core,cpu' to figure out the relation between core and
CPU numbers.

**Offline package 1**

On multi-socket systems there are multiple CPU packages. You can offline all CPUs
of a package to effectively "disable" it. Here is how to do it for package 1.

```bash
$ pepc cpu-hotplug offline --packages 1
```

## CPU Topology

The `pepc topology` command groups operations related to CPU topology, including non-compute die
details. This command is covered in a separate document: [Pepc User Guide:
Topology](guide-topology.md).

## PM QoS

The `pepc pmqos` command groups operations related to Linux PM QoS (Power Management Quality of
Service) settings. This includes reading and changing PM QoS latency limits.

The PM QoS latency limits can be set by user-space applications to inform the Linux kernel about
the required maximum latency. In current Linux kernels, this basically translates to CPU C-state
restrictions: Linux will not request C-states with latency higher than the specified limit on the
CPU where the limit is set.

Please refer to Linux PM QoS
[documentation](https://www.kernel.org/doc/html/latest/power/pm_qos_interface.html) for more
information.

### Examples

**Get All PM QoS Information**

```bash
$ pepc pmqos info
Source: Linux sysfs file-system
 - Linux per-CPU PM QoS latency limit: 0 (no limit) for all CPUs
Source: Linux character device node
 - Linux global PM QoS latency limit: 2000s
```

**Set Per-CPU Latency Limits**

Set latency limit to 100us for all CPUs in package 1, and also for CPU 0.

```bash
$ pepc pmqos config --latency-limit 100us --packages 1 --cpus 0
Linux per-CPU PM QoS latency limit: set to 100us for CPUs 0,56-111,168-223
```

Verify it.

```bash
$ pepc pmqos info
Source: Linux sysfs file-system
 - Linux per-CPU PM QoS latency limit: 100us for CPUs 0,56-111,168-223
 - Linux per-CPU PM QoS latency limit: 0 (no limit) for CPUs 1-55,112-167
Source: Linux character device node
 - Linux global PM QoS latency limit: 2000s
```

## TPMI

The `pepc tpmi` command groups operations related to TPMI. This command is covered in a separate
document: [Pepc User Guide: TPMI](guide-tpmi.md).

## ASPM

The `pepc aspm` command groups operations related to PCI Express Active State Power Management
(ASPM). ASPM is a power-saving feature that allows PCI Express links to enter low-power states when
idle.

ASPM is implemented in hardware and firmware, but Linux can enable or disable it globally or per PCIe
device.

### Examples

**Get Global ASPM Settings**

```bash
$ pepc aspm info
ASPM policy: default
Available policies: default, performance, powersave, powersupersave
```
