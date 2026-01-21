<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Pepc User Guide

- Author: Artem Bityutskiy <dedekind1@gmail.com>

## Table of Contents

- [Introduction](#introduction)
  - [Topology Options](#topology-options)
  - [Debug Options](#debug-options)
  - [YAML Output](#yaml-output)
  - [Mechanisms](#mechanisms)
  - [Getting Help](#getting-help)
  - [Remote Usage Model](#remote-usage-model)
  - [SUT Emulation](#sut-emulation)
- [P-states](#p-states)
  - [Examples](#examples)
- [C-states](#c-states)
  - [Examples](#examples-1)
- [Uncore](#uncore)
  - [Uncore Frequency and Dies](#uncore-frequency-and-dies)
  - [Examples](#examples-2)
- [CPU Hotplug](#cpu-hotplug)
  - [Examples](#examples-3)
- [CPU Topology](#cpu-topology)
  - [Examples](#examples-4)
- [PM QoS](#pm-qos)
  - [Examples](#examples-5)
- [TPMI](#tpmi)
  - [TPMI Mechanism Overview](#tpmi-mechanism-overview)
  - [TPMI Drivers](#tpmi-drivers)
  - [Debugfs Interface](#debugfs-interface)
  - [TPMI Spec Files](#tpmi-spec-files)
  - [Spec File Loading](#spec-file-loading)
  - [Examples](#examples-6)
- [ASPM](#aspm)
  - [Examples](#examples-7)

## Introduction

`pepc` command line interface is organized into **commands** and **subcommands**. The
commands are 'pstates', 'cstates', 'tpmi', and so on. Most commands have 'info' (read information)
and 'config' (change configuration) subcommands. However, some commands may have additional or
different subcommands.

### Topology Options

Many subcommands support topology options, such as '--cpus', '--cores', '--packages', etc. These
options select the target CPUs, cores, packages, or other topology elements for the operation.

### Debug Options

When you run into problems using `pepc`, you can enable debug output by adding the '-d' or
'--debug' option to any command. This will print additional debug information that may help
diagnose the problem, or just give you more insight into what `pepc` is doing behind the scenes.

You can limit the debug output to specific Python module names by using
'--debug-modules <module-names>'.

### YAML Output

The 'info' subcommand of most commands supports the '--yaml' option that prints the output in YAML
format, instead of the human-readable format. This is useful for scripting and automated parsing of
the output.

### Mechanisms

`pepc` uses various mechanisms to read and change power management settings. For example,
the 'pepc pstates config --max-freq 2GHz' command changes the maximum CPU frequency using the
'sysfs' mechanism.

Some options support only one mechanism, while others support multiple mechanisms. For example,
the 'pepc uncore info --min-freq' option supports two mechanisms - 'sysfs' and 'tpmi'. By default,
`pepc` tries to use the first mechanism in the list of supported mechanisms, and if it fails, it
tries the next one, and so on.

You can force `pepc` to use a specific mechanism or mechanisms with the '--mechanisms
<mechanism-name>' option.
For example, to read the minimum uncore frequency using the 'tpmi' mechanism, use:

```bash
pepc uncore info --min-freq --mechanisms tpmi
```

The list of supported mechanisms for every option is documented in the corresponding manual page.

Some options that sound similar but use different mechanisms are implemented as separate options.
For example, '--cppc-guaranteed-perf' and '--hwp-guaranteed-perf' are implemented as 2 different
options, instead of a single option with multiple mechanisms.

What is the criterion? The CPPC guaranteed performance and HWP guaranteed performance have similar
names, but they do not have to have the same value. Therefore, they are 2 separate options. On the
other hand, the 'pepc uncore info --min-freq' option supports both 'sysfs' and 'tpmi' mechanisms,
because the minimum uncore frequency is supposed to be the same when read via sysfs or TPMI.

**Note:** The difference between CPPC and HWP guaranteed performance levels is explained in the
[Intel CPU Base Frequency Explained](misc-cpu-base-freq.md) article.

### Getting Help

Each command and subcommand supports the '-h' or '--help' option that prints the help text for that
command or subcommand. For example, to get help about the 'pepc pstates config' subcommand, run:

```bash
pepc pstates config --help
```

The help text includes only a very brief options description. More detailed description is available
in the man pages. Each command and subcommand has a corresponding man page. Man pages are written in
reStructuredText (rst) format and are located in the [docs/](.) subdirectory of the `pepc` git
repository.

When `pepc` is installed, the 'rst' files are converted into formatted man pages and installed along
with the tool. When `pepc` is configured properly, you can access the man pages with the `man`
command, for example:

```bash
man pepc-uncore
```

Also remember, there are multiple articles about Linux and Intel CPU power management concepts
in the miscellaneous documentation files in the `pepc` repository (see [here](.)).

### Remote Usage Model

Most people run `pepc` to manage the local system (SUT - System Under Test). However, `pepc` can
also be used to configure remote SUTs over SSH. This is helpful when a single control machine is
used to manage multiple SUTs in a lab environment.

The remote usage scenario is as follows:
 - Install `pepc` on the control machine.
 - Configure passwordless root SSH access from the control machine to SUTs.
 - Run `pepc` with the '-H <SUT-name-or-IP>' option.

For example,

```bash
pepc pstates config -H <SUT-name-or-IP> --max-freq 2.0GHz
```

will log into '<SUT-name-or-IP>' over SSH as root and set the maximum CPU frequency limit to 2.0GHz on
that SUT.

### SUT Emulation

The `pepc` tool implements a small abstraction layer that allows running commands on a SUT,
regardless of whether it is local, remote (over SSH), or emulated.

SUT emulation is useful for development and testing purposes, because it allows running `pepc`
without real hardware access. SUT emulation is based on pre-recorded data from real systems.

The `pepc` repository includes emulation data for many types of server and client systems under the
'tests/emul-data/' subdirectory. For example, 'tests/emul-data/rpl0' includes emulation data for
a Raptor Lake client system.

To run a `pepc` command on an emulated Raptor Lake system, use the '-D rpl0' option. Keep in
mind, however, that emulation data are not installed along with `pepc`. Therefore, you need to clone
the `pepc` git repository and run `pepc` from there to use emulated SUTs.

Here is an example of running a `pepc` command on an emulated Raptor Lake system:

```bash
./pepc pstates info --max-freq -D rpl0
Max. CPU frequency: 4.60GHz for CPUs 0-7 (P-cores)
Max. CPU frequency: 3.40GHz for CPUs 8-15 (E-cores)
```

The `emulation-data-generator` tool, which is available in the `pepc` git repository, can be used
to collect and save emulation data from a real system. The emulation data should be placed under the
'tests/emul-data/' subdirectory of the `pepc` git repository.

## P-states

The `pepc pstates` command groups operations related to CPU performance states (P-states). For
example, it supports reading and changing CPU frequency limits.

If you are new to Intel CPU P-states, the [Intel CPU Base Frequency
Explained](misc-cpu-base-freq.md) article explains many concepts related to CPU performance scaling.

### Examples

**Get all P-states Information**

Here is an example of running `pepc pstates info` on a 2-socket Granite Rapids system.

```bash
$ pepc pstates info
Source: Linux sysfs file-system
 - Turbo: on
 - Min. CPU frequency: 800.00MHz for all CPUs
 - Max. CPU frequency: 3.90GHz for all CPUs
 - Min. supported CPU frequency: 800.00MHz for all CPUs
 - Max. supported CPU frequency: 3.90GHz for all CPUs
 - CPU base frequency: 2.00GHz for all CPUs
 - EPP: 'balance_performance' for all CPUs
 - EPB: 6 for all CPUs
 - CPU frequency driver: intel_pstate
 - Mode of 'intel_pstate' driver: active
 - CPU frequency governor: 'powersave' for all CPUs
 - Available CPU frequency governors: performance, powersave
 - ACPI CPPC lowest performance level: 5 for all CPUs
 - ACPI CPPC lowest nonlinear performance level: 8 for all CPUs
 - ACPI CPPC guaranteed performance level: 20 for all CPUs
 - ACPI CPPC nominal performance level: 20 for all CPUs
 - ACPI CPPC highest performance level: 39 for all CPUs
Source: Model Specific Register (MSR)
 - Fixed CPU base frequency: 2.00GHz
 - Hardware power management: on
 - HWP lowest performance level: 5 for all CPUs
 - HWP most efficient performance level: 8 for all CPUs
 - HWP guaranteed performance level: 20 for all CPUs
 - HWP highest performance level: 39 for all CPUs
Source: Hardware documentation
 - Bus clock speed: 100.00MHz
```

**Get CPU Base Frequency**

Here are 2 commands for getting the fixed and sysfs CPU base frequency on a Raptor Lake system.

```bash
# Fixed CPU base frequency
$ pepc pstates info --fixed-base-freq
Fixed CPU base frequency: 2.20GHz
# Sysfs CPU base frequency
$ pepc pstates info --base-freq
CPU base frequency: 1.90GHz for CPUs 0-7 (P-cores)
CPU base frequency: 1.40GHz for CPUs 8-15 (E-cores)
```

**Set Min. and Max. CPU Frequency for E-cores**

Here is how to limit CPU frequency range to [1.5GHz, 2GHz] for E-cores on a Raptor Lake system.

First, find out what CPUs are E-cores using the `pepc topology info` command.

```bash
$ pepc topology info
CPU    Core    Module    Node    Package    Hybrid
  0       0         0       0          0    P-core
  1       0         0       0          0    P-core
  2       4         1       0          0    P-core
  3       4         1       0          0    P-core
  4       8         2       0          0    P-core
  5       8         2       0          0    P-core
  6      12         3       0          0    P-core
  7      12         3       0          0    P-core
  8      16         4       0          0    E-core
  9      17         4       0          0    E-core
 10      18         4       0          0    E-core
 11      19         4       0          0    E-core
 12      20         5       0          0    E-core
 13      21         5       0          0    E-core
 14      22         5       0          0    E-core
 15      23         5       0          0    E-core
```

E-cores are CPUs 8-15. Now set the min. and max. CPU frequency for these CPUs.

```bash
$ pepc pstates config --min-freq 1.5GHz --max-freq 2GHz --cpus 8-15
Min. CPU frequency: set to 1.50GHz for CPUs 8-15 (E-cores)
Max. CPU frequency: set to 2.00GHz for CPUs 8-15 (E-cores)
```

Verify it.

```bash
$ pepc pstates info --min-freq --max-freq
Min. CPU frequency: 400.00MHz for CPUs 0-7 (P-cores)
Min. CPU frequency: 1.50GHz for CPUs 8-15 (E-cores)
Max. CPU frequency: 4.60GHz for CPUs 0-7 (P-cores)
Max. CPU frequency: 2.00GHz for CPUs 8-15 (E-cores)
```

**Lock CPU Frequency to Base Frequency**

Lock CPU frequency to sysfs base frequency (HFM) for all CPUs in package 1 on a 2-socket Granite
Rapids system.

```bash
$ pepc pstates config --min-freq base --max-freq base --packages 1
Min. CPU frequency: set to 2.00GHz for CPUs 128-255,384-511 (package 1)
Max. CPU frequency: set to 2.00GHz for CPUs 128-255,384-511 (package 1)
```

**Note:** You do not have to specify the exact base frequency value. You can simply use the 'base'
keyword, and `pepc` will figure out the correct value itself.

**Unlock CPU Frequency**

Unlock CPU frequency for all CPUs on a Raptor Lake system by setting min. and max. CPU frequency to
the supported minimum and maximum frequency.

```bash
$ pepc pstates config --min-freq min --max-freq max
Min. CPU frequency: set to 1.2GHz for CPUs 0-87 (all CPUs)
Max. CPU frequency: set to 3.6GHz for CPUs 0-87 (all CPUs)
```

**Change Linux CPU Frequency Governor**

First, get the name of current governor and list of supported governors.

```bash
$ pepc pstates info --governor --governors
CPU frequency governor: 'schedutil' for CPUs 0-87 (all CPUs)
Available CPU frequency governors: conservative, ondemand, userspace, powersave, performance, schedutil
```

Switch to the 'performance' governor.

```bash
$ pepc pstates config --governor performance
CPU frequency governor: set to 'performance' for CPUs 0-87 (all CPUs)
```

Verify it.

```bash
$ pepc pstates info --governor
CPU frequency governor: 'performance' for CPUs 0-87 (all CPUs)
```

## C-states

The `pepc cstates` command groups operations related to CPU idle states (C-states). For
example, it supports enabling or disabling requestable Linux C-states or toggling the CPU "C1
demotion" feature.

If you are new to Linux and Intel CPU C-states, the following articles available in the `pepc` repository
may be helpful:
- [Intel C-state namespaces](misc-cstate-namespaces.md) - explains C-state naming conventions.
- [Xeon C6P and C6SP Idle States](misc-c6p-c6sp.md) - explains the C6P and C6SP idle states on
  Intel Xeon platforms.

### Examples

**Get all C-states Information**

```bash
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

**Get information about C1, C1E autopromote, and C1 demotion**

```bash
$ pepc cstates info --cstates C1 --c1e-autopromote --c1-demotion
C1: 'on' for CPUs 0-87 (all CPUs)
 - description: MWAIT 0x00
 - expected latency: 2 us
 - target residency: 2 us
C1E autopromote: 'off' for CPUs 0-87 (all CPUs)
C1 demotion: 'off' for CPUs 0-87 (all CPUs)
```

**Toggle C-states**

Disable all C-states but POLL on all CPUs.

```bash
$ pepc cstates config --disable all --enable POLL
POLL: set to 'off' for CPUs 0-87 (all CPUs)
C1: set to 'off' for CPUs 0-87 (all CPUs)
C1E: set to 'off' for CPUs 0-87 (all CPUs)
C3: set to 'off' for CPUs 0-87 (all CPUs)
C6: set to 'off' for CPUs 0-87 (all CPUs)
POLL: set to 'on' for CPUs 0-87 (all CPUs)
```

Enable all C-states on all CPUs.

```bash
$ pepc cstates config --enable all
POLL: set to 'on' for CPUs 0-87 (all CPUs)
C1: set to 'on' for CPUs 0-87 (all CPUs)
C1E: set to 'on' for CPUs 0-87 (all CPUs)
C3: set to 'on' for CPUs 0-87 (all CPUs)
C6: set to 'on' for CPUs 0-87 (all CPUs)
```

Disable C1E and C6 on package 1.

```bash
$ pepc cstates config --disable C1E,C6 --packages 1
C1E: set to 'off' for CPUs 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47,49,51,53,55,57,59,61,63,65,67,69,71,73,75,77,79,81,83,85,87 (package 1)
C6: set to 'off' for CPUs 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47,49,51,53,55,57,59,61,63,65,67,69,71,73,75,77,79,81,83,85,87 (package 1)
```

**Configure package C-state limit**

Get package C-state limit information.

```bash
$ pepc cstates info --pkg-cstate-limit
Package C-state limit: 'PC6' for CPUs 0-87 (all CPUs)
Package C-state limit lock: 'off' for CPUs 0-87 (all CPUs)
Available package C-state limits: PC0, PC2, PC3, PC6, unlimited
```

Since package C-state limit MSR is not locked, we can modify the limit. Set the deepest
allowed package C-state to PC0 on all packages.

```bash
$ pepc cstates config --pkg-cstate-limit PC0 --packages all
Package C-state limit set to 'PC0' for CPUs 0-87 (all CPUs)
```

## Uncore

The `pepc uncore` command groups operations related to CPU uncore, for example reading or changing
uncore frequency limits.

"Uncore" is an informal term referring to the Intel CPU north complex blocks excluding the cores. For
example, it typically includes components like the last level cache (LLC), memory controller, and
north complex interconnects (e.g., between cores).

Some concepts related to uncore frequency scaling and the ELC (Efficiency Latency Control) feature
are explained in [Uncore ELC and Frequency Scaling](misc-uncore-elc.md).

### Uncore Frequency and Dies

In pepc, a "die" is considered to be a unit of uncore frequency scaling. In other words, uncore
frequency is per-die.

Dies that include CPU cores are referred to as compute dies. Some Intel CPUs enumerate compute dies
via the 'CPUID' instruction, and Linux exposes this information via sysfs (e.g.,
'/sys/devices/system/cpu/cpu179/topology/die_cpus_list'). Some Intel CPUs do not enumerate
compute dies via CPUID, and so Linux does not expose any die-related information in sysfs. In such
cases, `pepc` uses the platform-specific methods to figure out the die topology. For example, on
Granite Rapids Xeon, `pepc` uses MSR 0x54 (MSR_PM_LOGICAL_ID) to figure out which CPUs belong to
which compute die.

Some dies do not include CPUs, but still have uncore frequency scaling capability. For example,
on Granite Rapids Xeon there are "IO dies" that include uncore blocks related to PCIe and
CXL. Such dies are not discoverable via CPUID or sysfs, so `pepc` uses the TPMI mechanism to enumerate
non-compute dies and assign them unique die IDs.

**Note:** `pepc` dies do not correspond to physical silicon dies. This is more of a logical
concept used to group uncore frequency domains.

Typically client CPUs (e.g., Raptor Lake, Alder Lake) have a single compute die and no non-compute
dies. Many server CPUs (e.g., Ice Lake Xeon, Sapphire Rapids Xeon) have only a single compute die
and no non-compute dies as well. Some server CPUs (e.g., Cascade Lake-AP) have multiple compute dies
and no non-compute dies. Finally, newer server CPUs (e.g., Granite Rapids Xeon and Sierra Forest
Xeon) may have multiple compute dies and multiple non-compute dies.

Use `pepc topology info` to discover die topology on your system. Here is a Granite
Rapids example:

```bash
$ pepc topology info
CPU    Core    Die    Node    Package
  0       0      0       0          0
  1       1      0       0          0
  ... snip ...
 42      42      0       0          0
 43      64      1       0          0
 44      65      1       0          0
  ... snip ...
 85     106      1       0          0
 86     128      2       0          0
 87     129      2       0          0
  ... snip ...
127     169      2       0          0
128       0      0       1          1
129       1      0       1          1
... snip ...
511     169      2       1          1
  -       -      3       -          0
  -       -      4       -          0
  -       -      3       -          1
  -       -      4       -          1
```

The Granite Rapids has 512 CPUs, and the output is very long, so it is snipped. The important part
is to demonstrate that there are 3 compute dies per package (dies 0, 1, and 2), and there are also 2
I/O dies per package (dies 3 and 4) that do not have any CPUs. Package 1 also has dies 0,1,2,3,4.
In other words, die numbers are relative to the package, not globally unique. This follows the
Linux kernel die numbering convention.

### Examples

**Get All Uncore Information**

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

The Raptor Lake client system has only one compute die and no I/O dies, and it does not support ELC.

```bash
$ pepc uncore info
Source: Linux sysfs file-system
 - Min. uncore frequency: 400.00MHz for all CPUs
 - Max. uncore frequency: 4.00GHz for all CPUs
 - Min. supported uncore frequency: 400.00MHz for all CPUs
 - Max. supported uncore frequency: 4.00GHz for all CPUs
```

**Additional Examples**

For more examples related to uncore frequency scaling and ELC configuration, refer to the [Uncore ELC and Frequency Scaling](misc-uncore-elc.md) article.

## CPU Hotplug

The `pepc cpu-hotplug` command groups operations related to CPU hotplug functionality in Linux.
Today, this includes onlining and offlining CPUs.

What does CPU offline do in Linux? At high level, it migrates all tasks and interrupts away from the
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

The `pepc topology` command groups operations related to CPU topology discovery. Currently, it
supports only the 'info' subcommand that prints the CPU topology table.

### Examples

**Print the Topology Table**

Here is an example of running `pepc topology info` on an Alder Lake system.

```bash
$ pepc topology info
CPU    Core    Module    Node    Package    Hybrid
  0       0         0       0          0    P-core
  1       0         0       0          0    P-core
  2       4         1       0          0    P-core
  3       4         1       0          0    P-core
  4       8         2       0          0    P-core
  5       8         2       0          0    P-core
  6      12         3       0          0    P-core
  7      12         3       0          0    P-core
  8      16         4       0          0    E-core
  9      17         4       0          0    E-core
 10      18         4       0          0    E-core
 11      19         4       0          0    E-core
 12      20         5       0          0    E-core
 13      21         5       0          0    E-core
 14      22         5       0          0    E-core
 15      23         5       0          0    E-core
```

The table gives an idea about how CPU, core, NUMA node and package numbers are related to each
other.

**Discover Dies**

To discover compute and I/O dies on a Granite Rapids system, run:

```bash
$ pepc topology info --columns package,die,node --packages 0
Package    Die    Node
      0      0       0
      0      1       0
      0      2       0
      0      3       -
      0      4       -
```

The output is limited to package 0 for brevity. The '-' in the Node column indicates that dies 3 and 4
do not have any CPUs, and therefore are not associated with any NUMA node and hence, they are not
compute dies.

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

The `pepc tpmi` command groups operations related to TPMI.

TPMI stands for Topology Aware Register and PM Capsule Interface. It provides a standardized way for
software to discover, configure, and control various PM (Power Management) features. Today, TPMI is
only available on server platforms starting from Granite Rapids and Sierra Forest Xeon.

The advantage of the TPMI mechanism over the traditional MSR mechanism is that TPMI is enumerable
and MMIO-based. This means that any CPU can read and write TPMI registers of any uncore domain.
In contrast, with MSRs, the 'RDMSR' or 'WRMSR' instructions must be executed on a CPU that belongs to
the target uncore domain (which is not even possible for non-compute dies that do not have any
CPUs).

### TPMI Mechanism Overview

The TPMI mechanism is based on PCIe MMIO: Intel processors expose one or multiple TPMI PCIe devices,
which are enumerable by Linux. These devices expose various hardware registers using the standard
PCIe VSEC (Vendor Specific Extended Capability) mechanism. Essentially, VSEC is a standard way to
put vendor-specific data into PCIe configuration space.

TPMI registers are grouped into features. For example, the UFS (Uncore Frequency Scaling) feature
(feature ID 2) includes registers for managing uncore frequency scaling. One TPMI device typically
includes multiple features.

There may be multiple copies of the same feature in a TPMI device, and these copies are referred to
as instances.

For example, on a Granite Rapids system, there may be up to 5 dies, each having its own UFS feature
instance, resulting in 5 copies of UFS feature registers in the TPMI device, one per die. This
allows software to manage uncore frequency scaling on a per-die basis.

For all TPMI features except UFS, there is only one copy of registers per instance. The hierarchy
is:

```
TPMI devices
└── Features
    └── Instances
        └── Registers
```

However, UFS is special. A UFS instance may consist of multiple clusters. UFS registers include 2
read-only header registers (`UFS_HEADER` and `UFS_FABRIC_CLUSTER_OFFSET`) and several control
registers (e.g., `UFS_STATUS`, `UFS_CONTROL`). There is always only one copy of header registers
per UFS instance, but there may be multiple copies of control registers per UFS instance, one per
cluster.

On the Granite Rapids platform there is only one cluster per UFS instance. However, future
platforms may include multiple clusters per UFS instance to support more complex uncore
topologies.

The UFS feature hierarchy is:

```
TPMI devices
└── UFS feature
    └── Instances
        ├── Header registers (one copy)
        └── Clusters
            └── Control registers (one copy per cluster)
```

### TPMI Drivers

Different TPMI features may be managed by different Linux kernel drivers. For example, the UFS feature is
handled by the `intel_uncore_freq_tpmi` driver, and the SST feature is handled by the
`intel_speed_select_tpmi` driver.

The generic `intel_tpmi` driver is responsible for enumerating TPMI devices and features, and it
also exposes the entire TPMI device register space via 'debugfs' (typically mounted at
'/sys/kernel/debug'), allowing user-space tools to discover, read, and write to any TPMI register.

### Debugfs Interface

Today, the 'tpmi' mechanism in `pepc` uses the TPMI debugfs interface to read and write TPMI
registers. Here is an example of TPMI debugfs layout on a Granite Rapids system:

```bash
$ ls /sys/kernel/debug/ | grep tpmi
tpmi-0000:00:03.1
tpmi-0000:80:03.1
```

These are 2 TPMI devices. Each TPMI device directory includes multiple files, one per feature. For
example (snipped for brevity):

```bash
$ ls -1 /sys/kernel/debug/tpmi-0000\:00\:03.1/
pfs_dump
plr
tpmi-id-00
tpmi-id-01
tpmi-id-02
... snip ...
```

The 'tpmi-id-02' directory corresponds to the UFS feature (feature ID 2). It includes two files, one for
reading registers and another for writing registers:

```bash
$ ls -1 /sys/kernel/debug/tpmi-0000\:00\:03.1/tpmi-id-02/
mem_dump
mem_write
```

The 'mem_dump' file contains all instances of the UFS feature. Here is an example, snipped for
brevity:

```bash
$ cat /sys/kernel/debug/tpmi-0000\:00\:03.1/tpmi-id-02/mem_dump
TPMI Instance:0 offset:0x90004000
 00000000: 00000102 00000002 00000002 00000000 038ac50c 00014365 03041601 0000788d
 00000020: 00000604 00000000 ffff0504 00000000
 ... snip ...
TPMI Instance:4 offset:0x900040c0
 00000000: 00000102 00000002 00000002 00000000 040ac608 0cff80dc 02041901 0000788d
 00000020: 00000504 00000000 ffff0504 00000000
```

The 'mem_write' file can be used to write to UFS registers. The writes are in the
'<instance>,<offset>,<value>' format.

### TPMI Spec Files

The Linux kernel exposes raw TPMI registers via debugfs. However, to make sense of these registers,
`pepc` needs to know the register layout, i.e., which register is at which offset, what each register
bit means, etc. This is what TPMI spec files are for.

TPMI spec files are YAML files that describe TPMI features and their registers. They are available
in the `pepc` git repository under the ['pepcdata/tpmi/'](../pepcdata/tpmi/) subdirectory.

The spec files are grouped by platform families, because newer platforms may bring new TPMI
features or extend existing features. Currently, there are only Granite Rapids Xeon family spec
files available in ['pepcdata/tpmi/gnr'](../pepcdata/tpmi/gnr). The
['index.yml'](../pepcdata/tpmi/index.yml) file maps platform families to their corresponding spec
subdirectories.

Here is the spec file for the UFS feature:
['pepcdata/tpmi/gnr/ufs.yml'](../pepcdata/tpmi/gnr/ufs.yml). It includes definitions for UFS
registers and register bit fields, including a description for each field.

The TPMI spec file format is `pepc`-specific, invented by the `pepc` developers. This is not an
official Intel format. These files are generated from Intel internal TPMI XML description
files using the `tpmi-spec-files-generator` tool, which is available in the `pepc` git repository.

**Note:** `pepc` git repository provides TPMI files only for some TPMI features, e.g., UFS and SST.
While the most important features are covered, not all TPMI features are supported.

### Spec File Loading

When running a `pepc tpmi` command, `pepc` first searches for TPMI spec files. Spec files are
installed along with `pepc`, so they are typically found in one of the standard locations.

It is possible to override the default spec file search path using the `PEPC_TPMI_DATA_PATH`
environment variable. For example, if you have a custom or a non-public version of the 'ufs.yml'
spec file, you can place it under a custom directory, e.g.,
'/home/user/tpmi-data/gnr/ufs.yml', copy the standard 'index.yml' file to '/home/user/tpmi-data/index.yml',
and then set the environment variable as follows:

```bash
$ export PEPC_TPMI_DATA_PATH=/home/user/tpmi-data
```

This overrides only the standard 'ufs.yml' file with your custom version. Other spec
files are not overridden, and `pepc` will use the standard spec files for other features.

### Examples

**List Available TPMI Features**

Here is how to list all available TPMI features on a Granite Rapids system.

```bash
$ pepc tpmi ls
 - tpmi_info: TPMI Info Registers
 - rapl: Running Average Power Limit (RAPL) reporting and control
 - ufs: Processor uncore (fabric) monitoring and control
 - sst: Intel Speed Select Technology (SST) control
 ```

 The list is rather short because it is limited by the available TPMI spec files. Include the
 `--unknown` option to list all discovered TPMI features, even those without spec files.

 ```bash
$ pepc tpmi ls --unknown
Supported TPMI features
 - tpmi_info: TPMI Info Registers
 - rapl: Running Average Power Limit (RAPL) reporting and control
 - ufs: Processor uncore (fabric) monitoring and control
 - sst: Intel Speed Select Technology (SST) control
Unknown TPMI features (available, but no spec file found)
 - 0x80, 0x1, 0x3, 0x4, 0xa, 0x6, 0xc, 0xd, 0xfd, 0xfe, 0xff, 0x80, 0x1, 0x3, 0x4, 0xa, 0x6, 0xc, 0xd, 0xfd, 0xfe, 0xff
 ```

**Read All TPMI Registers**

You can read all TPMI registers of every discovered feature by running `pepc tpmi read` without any
options. However, the output is very long.

To limit the output, use one of the filtering options: '--features', '--addresses', '--packages',
'--instances', '--clusters', '--registers', '--bitfields'.

**Display TPMI Topology**

To see how TPMI devices, packages, and instances are organized on your system, use the `--topology`
option:

```bash
$ pepc tpmi ls --topology -F ufs
- ufs: Processor uncore (fabric) monitoring and control
  - PCI address: 0000:00:03.1
    Package: 0
    Instances: 0-4
  - PCI address: 0000:80:03.1
    Package: 1
    Instances: 0-4
```

This shows the PCI addresses of TPMI devices, which packages they belong to, and the instance
numbers for each device.

**Read a TPMI Register**

This example reads the 'UFS_STATUS' register of the UFS feature for package 0, instance 4 on a
Granite Rapids system:

```bash
$ pepc tpmi read -F ufs --registers UFS_STATUS --packages 0 --instances 4
- TPMI feature: ufs
  - PCI address: 0000:00:03.1
    Package: 0
    - Instance: 4
      - Cluster: 0
        - UFS_STATUS: 0x279ff040ada88
          - CURRENT_RATIO[6:0]: 8
          - CURRENT_VOLTAGE[22:7]: 5557
          - AGENT_TYPE_CORE[23:23]: 0
          - AGENT_TYPE_CACHE[24:24]: 0
          - AGENT_TYPE_MEMORY[25:25]: 0
          - AGENT_TYPE_IO[26:26]: 1
          - RSVD[31:27]: 0
          - THROTTLE_COUNTER[63:32]: 162303
```

Note that for UFS feature, the output includes cluster information. UFS is special because a UFS
instance may consist of multiple clusters, each with its own copy of control registers (like
`UFS_STATUS`). Header registers (`UFS_HEADER` and `UFS_FABRIC_CLUSTER_OFFSET`) are shown only once
per instance under cluster 0.

**Note:** On Granite Rapids, instance numbers typically correspond to die numbers (instance 0 = die
0, instance 1 = die 1, etc.), but this mapping is platform-specific.

**Read TPMI Bit Fields**

This example reads the 'TIME_WINDOW' and 'PWR_LIM_EN' bit fields of the
'SOCKET_RAPL_PL1_CONTROL' register:

```bash
$ pepc tpmi read -F rapl --registers SOCKET_RAPL_PL1_CONTROL --bitfields TIME_WINDOW,PWR_LIM_EN
- TPMI feature: rapl
  - PCI address: 0000:00:03.1
    Package: 0
    - Instance: 0
      - SOCKET_RAPL_PL1_CONTROL: 0x4000000000280fa0
        - TIME_WINDOW[24:18]: 10
        - PWR_LIM_EN[62:62]: 1
  - PCI address: 0000:80:03.1
    Package: 1
    - Instance: 0
      - SOCKET_RAPL_PL1_CONTROL: 0x4000000000280fa0
        - TIME_WINDOW[24:18]: 10
        - PWR_LIM_EN[62:62]: 1
```

Since packages and instances were not limited, the output includes all packages and instances.

**Write a TPMI Bit Field**

This example changes the maximum uncore frequency ratio for package 0, instance 2 (die 2) on a
Granite Rapids system:

```bash
$ pepc tpmi write -F ufs --packages 0 --instances 2 --register UFS_CONTROL --bitfield MAX_RATIO -V 20
Wrote '20' to TPMI register 'UFS_CONTROL', bit field 'MAX_RATIO' (feature 'ufs', device '0000:00:03.1', package 0, instance 2, cluster 0)
```

Note that the write command includes cluster information in the output. For UFS, when no cluster is
specified, the command writes to cluster 0 by default.

**Note:** The value 20 corresponds to a 2.0GHz maximum uncore frequency (ratio × 100MHz bus clock).

**Write to Multiple Instances**

You can write to all instances of a package by omitting the `--instances` option:

```bash
$ pepc tpmi write -F ufs --packages 0 --register UFS_CONTROL --bitfield MAX_RATIO -V 20
Wrote '20' to TPMI register 'UFS_CONTROL', bit field 'MAX_RATIO' (feature 'ufs', device '0000:00:03.1', package 0, instance 0, cluster 0)
Wrote '20' to TPMI register 'UFS_CONTROL', bit field 'MAX_RATIO' (feature 'ufs', device '0000:00:03.1', package 0, instance 1, cluster 0)
Wrote '20' to TPMI register 'UFS_CONTROL', bit field 'MAX_RATIO' (feature 'ufs', device '0000:00:03.1', package 0, instance 2, cluster 0)
```

**Write to Specific UFS Clusters**

On Granite Rapids, there is only one cluster per UFS instance. However, future platforms may
support multiple clusters per instance. On such platforms, you can write to specific clusters using
the `--clusters` option:

```bash
# This would only work on platforms with multiple clusters per instance.
$ pepc tpmi write -F ufs --packages 0 --instances 2 --clusters 1 --register UFS_CONTROL --bitfield MAX_RATIO -V 18
Wrote '18' to TPMI register 'UFS_CONTROL', bit field 'MAX_RATIO' (feature 'ufs', device '0000:00:03.1', package 0, instance 2, cluster 1)
```

**YAML Output**

For programmatic consumption or integration with other tools, TPMI information can be output in YAML
format using the `--yaml` option:

```bash
$ pepc tpmi read -F ufs --registers UFS_STATUS --packages 0 --instances 4 --yaml
ufs:
  '0000:00:03.1':
    package: 0
    instances:
      4:
        0:
          UFS_STATUS:
            value: 0x279ff040ada88
            fields:
              CURRENT_RATIO: 8
              CURRENT_VOLTAGE: 5557
              AGENT_TYPE_CORE: 0
              AGENT_TYPE_CACHE: 0
              AGENT_TYPE_MEMORY: 0
              AGENT_TYPE_IO: 1
              RSVD: 0
              THROTTLE_COUNTER: 162303
```

**Filtering with --no-bitfields**

When you only need register values without decoding bit fields, use the `--no-bitfields` option to
simplify the output:

```bash
$ pepc tpmi read -F ufs --registers UFS_STATUS --packages 0 --instances 4 --no-bitfields
- TPMI feature: ufs
  - PCI address: 0000:00:03.1
    Package: 0
    - Instance: 4
      - Cluster: 0
        - UFS_STATUS: 0x279ff040ada88
```
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
