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
- [Examples](#examples)
  - [Display CPU Topology](#display-cpu-topology)
  - [Display Topology for Specific Package](#display-topology-for-specific-package)
  - [Select Specific Columns](#select-specific-columns)
  - [Customize Column Order](#customize-column-order)
  - [Display Non-Compute Dies Details](#display-non-compute-dies-details)

## Introduction

The `pepc topology` provides operations to discover and display CPU topology information, including
non-compute die details.

There is only one subcommand available: `info` - it displays the CPU topology table. By default, the
table includes all scopes relevant to the system. For example:
- On a non-hybrid client system with a single package, no modules or dies, the output will include
   only CPU, core, and NUMA node scopes.
- On a hybrid system, the output will also include the "hybrid" column to distinguish between core
  types (E-core, P-core, etc.).
- On a multi-package Granite Rapids Xeon system, the output will also include package and
  die scopes. It will also include the "DieType" column to distinguish between compute and non-compute
  dies (there are I/O dies on Granite Rapids, which do not have CPUs, but have PCIe controllers and
  frequency control knobs).

But you can customize the output by specifying which scopes to include or exclude using the
'--columns' option.

The order of the columns in the output table follows the hierarchy of scopes from the most
fine-grained (CPU) to the most coarse-grained (Package). The 'Hybrid' and 'DieType' columns are always
displayed at the end of the table. Use the '--order' option to change the order of the columns.

Additionally, you can limit the output to certain CPUs, cores, modules, dies, packages, and
NUMA nodes using one of the target scope selection options: '--cpus', '--cores', etc.

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

The table gives an idea about how CPUs, cores, NUMA nodes and packages are related to each other.

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

### Display Non-Compute Dies Details

Here is an example of how to get detailed non-compute dies information on a Granite Rapids Xeon
system. The output is limited to package 1 only.

```bash
$ ./pepc topology info --dies-info --package 1 -D gnr0
Compute dies: package 1, dies 0, 1, 2
Non-Compute dies: package 1, dies 3, 4
Non-compute dies details:
  - Package 0:
    - Die 3 (I/O):
      TPMI Address: 0000:00:03.1
      TPMI Instance: 3
      TPMI Cluster: 0
      TPMI Agent type(s): io
    - Die 4 (I/O):
      TPMI Address: 0000:00:03.1
      TPMI Instance: 4
      TPMI Cluster: 0
      TPMI Agent type(s): io
  - Package 1:
    - Die 3 (I/O):
      TPMI Address: 0000:80:03.1
      TPMI Instance: 3
      TPMI Cluster: 0
      TPMI Agent type(s): io
    - Die 4 (I/O):
      TPMI Address: 0000:80:03.1
      TPMI Instance: 4
      TPMI Cluster: 0
      TPMI Agent type(s): io
```

This gives detailed information about each non-compute die, including its type, TPMI address, instance,
and cluster.

On Granite Rapids Xeon there are 2 I/O dies per package. However, future Intel platforms may have
more die types, for example a memory die.

Compute dies contain CPUs and are enumerated by the hardware via the `CPUID` instruction or via
MSR 0x54 (`MSR_PM_LOGICAL_ID`). Compute die IDs are assigned by the hardware.

Non-compute dies do not contain CPUs. The `pepc` tool enumerates them via TPMI and assigns die IDs,
so die IDs come from `pepc`, not from hardware.
