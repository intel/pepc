<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Pepc User Guide: Topology

- Author: Artem Bityutskiy \<dedekind1@gmail.com\>

## Table of Contents

- [Introduction](#introduction)
- [Die Topology and Die IDs](#die-topology-and-die-ids)
- [Examples](#examples)
  - [Display CPU Topology](#display-cpu-topology)
  - [Display Topology for Specific Package](#display-topology-for-specific-package)
  - [Select Specific Columns](#select-specific-columns)
  - [Customize Column Order](#customize-column-order)

## Introduction

The `pepc topology` command provides operations to discover and display CPU topology information,
including non-compute die details.

There is only one subcommand available: `info` - it displays the CPU topology table. By default, the
table includes all scopes relevant to the system. For example:
- On a non-hybrid client system with a single package, no modules or dies, the output will include
   only CPU, core, and NUMA node scopes.
- On a hybrid system, the output will also include the "hybrid" column to distinguish between core
  types (E-core, P-core, etc.).
- On a multi-package Granite Rapids Xeon system, the output will also include package and
  die scopes. It will also include the "DieType" column to distinguish between compute and
  non-compute dies (I/O dies on Granite Rapids Xeon do not have CPUs, but have PCIe controllers and
  uncore control).

But you can customize the output by specifying which scopes to include or exclude using the
'--columns' option.

The order of the columns in the output table follows the hierarchy of scopes from the most
fine-grained (CPU) to the most coarse-grained (Package). The 'Hybrid' and 'DieType' columns are always
displayed at the end of the table. Use the '--order' option to change the order of the columns.

Additionally, you can limit the output to certain CPUs, cores, modules, dies, packages, and
NUMA nodes using one of the target scope selection options: '--cpus', '--cores', etc.

## Die Topology and Die IDs

In pepc, a "die" is a unit of uncore control. It does not necessarily correspond to a physical die
on the CPU package.

### Compute Dies

Dies that include CPU cores are called compute dies. Intel CPUs may enumerate compute dies using
different methods:
- `CPUID` instruction: Some Intel CPUs expose die information via the `CPUID` instruction.
  Linux provides this information in sysfs (e.g.,
  '/sys/devices/system/cpu/cpu0/topology/die_cpus_list').
- MSR: Some Intel CPUs (e.g., Granite Rapids Xeon) do not expose die
  information via `CPUID`. In such cases, `pepc` uses MSR 0x54 (`MSR_PM_LOGICAL_ID`) to determine
  which CPUs belong to which compute die. The "domain ID" field from this MSR is used as the die ID.

In both cases, compute die IDs come from hardware and have specific hardware meaning.

### Non-Compute Dies

Some dies do not include CPU cores but still have uncore frequency control. For example:
- I/O dies: On Granite Rapids and Sierra Forest Xeon, I/O dies include PCIe and CXL controllers
  and have their own uncore frequency control.
- Future Intel platforms may include memory dies or other specialized die types with uncore
  control.

Non-compute dies cannot be discovered via `CPUID` or standard Linux sysfs interfaces because they
have no CPUs. Instead, `pepc` uses TPMI (Topology Aware Register and PM Capsule Interface) to
enumerate them. For more information about TPMI, see the [Pepc User Guide: TPMI](guide-tpmi.md).

Non-compute die IDs are sequential numbers (starting from the highest compute die ID + 1) assigned
by `pepc` for identification purposes. These IDs have no special hardware meaning - they are simply
used within `pepc` to uniquely identify non-compute dies. Under the hood, `pepc` maps them to TPMI
device addresses and uncore frequency control sysfs paths.

### Die Topology Examples

Typical die configurations on Intel CPUs:
- Client CPUs (e.g., Raptor Lake, Alder Lake): Single compute die, no non-compute dies.
- Single-die server CPUs (e.g., Ice Lake Xeon, Sapphire Rapids Xeon): Single compute die, no
  non-compute dies.
- Multi-die server CPUs without I/O dies (e.g., Cascade Lake-AP): Multiple compute dies, no
  non-compute dies.
- Multi-die server CPUs with I/O dies (e.g., Granite Rapids Xeon, Sierra Forest Xeon): Multiple
  compute dies and multiple non-compute dies (I/O dies).

The examples below demonstrate how `pepc topology info` displays these different configurations.

## Examples

### Display CPU Topology

Here is an example of running `pepc topology info` on an Alder Lake system.

```bash
$ pepc topology info
CPU    Core    Module    Hybrid
  0       0         0    P-core
  1       0         0    P-core
  2       4         1    P-core
  3       4         1    P-core
  4       8         2    P-core
  5       8         2    P-core
  6      12         3    P-core
  7      12         3    P-core
  8      16         4    E-core
  9      17         4    E-core
 10      18         4    E-core
 11      19         4    E-core
 12      20         5    E-core
 13      21         5    E-core
 14      22         5    E-core
 15      23         5    E-core
```

This table shows how CPUs, cores, and modules are organized on a hybrid system with both P-cores
and E-cores.

### Display Topology for Specific Package

To display the topology table only for package 0, use the `--packages 0` option. Here is a Granite
Rapids Xeon example (stripped for brevity):

```bash
$ pepc topology info --packages 0
CPU    Core    Die    Package    DieType
  0       0      0          0    Compute
  1       1      0          0    Compute
  2       2      0          0    Compute
  ... snip ...
382     168      2          0    Compute
383     169      2          0    Compute
  -       -      3          0      I/O
  -       -      4          0      I/O
```

If there are non-compute dies (like I/O dies on Granite Rapids), they will be listed at the end of the
output. The CPU, Core, and Node columns have '-' values for non-compute dies since they do not have
CPUs.

### Select Specific Columns

Here is an example of limiting the output to only package and die scopes. The 'DieType' column is
also automatically included since there are non-compute dies in the system.

```bash
$ pepc topology info --columns package,die,dtype
Package    Die    DieType
      0      0    Compute
      0      1    Compute
      0      2    Compute
      1      0    Compute
      1      1    Compute
      1      2    Compute
      0      3      I/O
      0      4      I/O
      1      3      I/O
      1      4      I/O
```

### Customize Column Order

Here is an example on a Lunar Lake system of sorting the output by module number, and including only
Module, CPU, and Hybrid columns.

```bash
$ pepc topology info --order module --columns module,cpu,hybrid
Module    CPU    Hybrid
     0      0    P-core
     1      1    P-core
     2      2    P-core
     3      3    P-core
     8      4    LPE-core
     8      5    LPE-core
     8      6    LPE-core
     8      7    LPE-core
```
