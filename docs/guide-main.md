<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Pepc User Guide

- Author: Artem Bityutskiy \<dedekind1@gmail.com\>

## Table of Contents

- [Introduction](#introduction)
  - [Target CPU Options](#target-cpu-options)
  - [Debug Options](#debug-options)
  - [YAML Output](#yaml-output)
  - [Mechanisms](#mechanisms)
  - [Getting Help](#getting-help)
  - [Remote Usage Model](#remote-usage-model)
  - [SUT Emulation](#sut-emulation)
- [P-states](#p-states)
- [C-states](#c-states)
- [Uncore](#uncore)
- [CPU Hotplug](#cpu-hotplug)
  - [Examples](#examples-3)
- [CPU Topology](#cpu-topology)
- [PM QoS](#pm-qos)
  - [Examples](#examples-4)
- [TPMI](#tpmi)
- [ASPM](#aspm)
  - [Examples](#examples-5)

## Introduction

`pepc` command line interface is organized into **commands** and **subcommands**. The
commands are 'pstates', 'cstates', 'tpmi', and so on. Most commands have 'info' (read information)
and 'config' (change configuration) subcommands. However, some commands may have additional or
different subcommands.

### Target CPU Options

By default, most `pepc` commands and subcommands operate on all CPUs. But you can limit the
operation target CPUs ('--cpus'), cores ('--cores'), modules ('--modules'), dies ('--dies'),
packages ('--packages') or NUMA nodes ('--nodes'). You also can limit the operation to specific core
siblings ('--core-siblings') or module siblings ('--module-siblings').

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

The list of supported mechanisms for each option is documented in the corresponding manual page.

Some options that sound similar but use different mechanisms are implemented as separate options.
For example, '--cppc-guaranteed-perf' and '--hwp-guaranteed-perf' are implemented as 2 different
options, instead of a single '--guaranteed-perf' option with multiple mechanisms.

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

The `pepc pstates` command groups operations related to CPU performance states (P-states). This
command is covered in a separate document: [Pepc User Guide: P-states](guide-pstates.md).

## C-states

The `pepc cstates` command groups operations related to CPU idle states (C-states). This command is
covered in a separate document: [Pepc User Guide: C-states](guide-cstates.md).

## Uncore

The `pepc uncore` command groups operations related to CPU uncore, for example reading or changing
uncore performance scaling settings. This command is covered in a separate document:
[Pepc User Guide: Uncore](guide-uncore.md).

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
