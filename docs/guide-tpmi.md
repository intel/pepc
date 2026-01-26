<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Pepc User Guide: TPMI

- Author: Artem Bityutskiy \<dedekind1@gmail.com\>

## Table of Contents

- [Introduction](#introduction)
- [TPMI Overview](#tpmi-overview)
  - [TPMI Drivers](#tpmi-drivers)
  - [Debugfs Interface](#debugfs-interface)
- [`pepc` TPMI Spec Files](#pepc-tpmi-spec-files)
  - [Spec File Loading](#spec-file-loading)
- [`pepc tpmi` Usage](#pepc-tpmi-usage)
  - [Live System Usage](#live-system-usage)
    - [Examples](#examples)
  - [TPMI debugfs Dump Decoding](#tpmi-debugfs-dump-decoding)
    - [How To Construct VFM](#how-to-construct-vfm)
    - [Examples](#examples-1)

## Introduction

The `pepc tpmi` command provides operations for working with TPMI (Topology Aware Register and PM
Capsule Interface). This document explains the TPMI mechanism and how to use the `pepc tpmi`
command.

## TPMI Overview

TPMI (Topology Aware Register and PM Capsule Interface) provides a standardized way for software to
discover, configure, and control various PM (Power Management) features. TPMI is available on Intel
server platforms starting from Granite Rapids and Sierra Forest Xeon.

TPMI has advantages over the traditional MSR mechanism: it is enumerable and MMIO-based. This means
any CPU can read and write TPMI registers of any uncore domain. In contrast, MSRs require executing
'RDMSR' or 'WRMSR' instructions on a CPU belonging to the target uncore domain, which is impossible
for non-compute dies that have no CPUs.

TPMI uses PCIe MMIO: Intel processors expose one or more TPMI PCIe devices that are enumerable by
Linux. These devices expose hardware registers using the standard PCIe VSEC (Vendor Specific
Extended Capability) mechanism, which provides a standard way to include vendor-specific data in
PCIe configuration space.

TPMI registers are grouped into features. For example, the UFS (Uncore Frequency Scaling) feature
(feature ID 2) includes registers for managing uncore frequency scaling. A TPMI device typically
contains multiple features.

Multiple copies of the same feature may exist in a TPMI device; these copies are called instances.

For example, a Granite Rapids system may have up to 5 dies, each with its own UFS instance. This
results in 5 copies of UFS registers in the TPMI device (one per die), allowing software to manage
uncore frequency scaling on a per-die basis.

For all TPMI features except UFS, there is only one copy of registers per instance. The hierarchy
is:

```
TPMI devices
└── Features
    └── Instances
        └── Registers
```

However, UFS is special: a UFS instance may contain multiple clusters. UFS registers include 2
read-only header registers (`UFS_HEADER` and `UFS_FABRIC_CLUSTER_OFFSET`) and several control
registers (e.g., `UFS_STATUS`, `UFS_CONTROL`). Each UFS instance has one copy of header registers,
but may have multiple copies of control registers (one per cluster).

Granite Rapids has one cluster per UFS instance, but future platforms may include multiple clusters
per instance to support more complex uncore topologies.

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

Different Linux kernel drivers manage different TPMI features. For example, the `intel_uncore_freq_tpmi`
driver handles UFS, and the `intel_speed_select_tpmi` driver handles SST.

The generic `intel_tpmi` driver enumerates TPMI devices and features, and exposes the entire TPMI
device register space via debugfs (typically mounted at '/sys/kernel/debug'), allowing user-space
tools to discover, read, and write TPMI registers.

### Debugfs Interface

The `pepc` TPMI implementation uses the TPMI debugfs interface to read and write registers. Here is
an example of the TPMI debugfs layout on a Granite Rapids system:

```bash
$ ls /sys/kernel/debug/ | grep tpmi
tpmi-0000:00:03.1
tpmi-0000:80:03.1
```

These are 2 TPMI devices. Each TPMI device directory contains multiple subdirectories, one per
feature. For example (snipped for brevity):

```bash
$ ls -1 /sys/kernel/debug/tpmi-0000\:00\:03.1/
pfs_dump
plr
tpmi-id-00
tpmi-id-01
tpmi-id-02
... snip ...
```

The 'tpmi-id-02' directory corresponds to the UFS feature (feature ID 2). It contains two files for
reading and writing registers:

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

## `pepc` TPMI Spec Files

The Linux kernel exposes raw TPMI registers via debugfs. To interpret these registers, `pepc`
needs the register layout: which register is at which offset, what each register bit means, etc.
This information is provided by TPMI spec files.

TPMI spec files are YAML files describing TPMI features and their registers. They are available in
the `pepc` git repository under the ['pepcdata/tpmi/'](../pepcdata/tpmi/) subdirectory.

Spec files are grouped by platform family, as newer platforms may introduce new TPMI features or
extend existing ones. Currently, only Granite Rapids Xeon family spec files are available in
['pepcdata/tpmi/gnr'](../pepcdata/tpmi/gnr). The ['index.yml'](../pepcdata/tpmi/index.yml) file
maps platform families to their spec subdirectories.

Here is the spec file for the UFS feature:
['pepcdata/tpmi/gnr/ufs.yml'](../pepcdata/tpmi/gnr/ufs.yml). It includes definitions for UFS
registers and register bit fields, including a description for each field.

The TPMI spec file format is specific to `pepc` and was created by the `pepc` developers. It is not
an official Intel format. These files are generated from Intel internal TPMI XML descriptions using
the `tpmi-spec-files-generator` tool available in the `pepc` git repository.

**Note:** The `pepc` git repository provides TPMI spec files only for selected features (e.g., UFS
and SST). While the most important features are covered, not all TPMI features are supported.

### Spec File Loading

When running `pepc tpmi` commands, `pepc` searches for TPMI spec files in standard installation
locations where they are installed along with `pepc`.

You can override the default spec file search path using the `PEPC_TPMI_DATA_PATH` environment
variable. For example, if you have a custom or non-public version of 'ufs.yml', place it in a
custom directory (e.g., '/home/user/tpmi-data/gnr/ufs.yml'), copy the standard 'index.yml' file to
'/home/user/tpmi-data/index.yml', and set the environment variable:

```bash
$ export PEPC_TPMI_DATA_PATH=/home/user/tpmi-data
```

This overrides only the standard 'ufs.yml' file with your custom version. Other spec
files are not overridden, and `pepc` will use the standard spec files for other features.

## `pepc tpmi` Usage

The `pepc tpmi` command supports two usage scenarios:
1. Reading and writing TPMI registers on a live system.
2. Decoding TPMI debugfs dumps captured from other systems.

### Live System Usage

The typical workflow for `pepc tpmi` is:
1. Discover available TPMI features using `pepc tpmi ls`.
  - Use `--topology` to see how TPMI devices and instances are organized.
  - Use `--list-specs` to view available TPMI spec files.
  - Use `--yaml` for machine-readable output.
2. Read TPMI registers using `pepc tpmi read`, filtering by feature, package, instance, cluster,
   register, or bit field as needed.
3. Write TPMI registers using `pepc tpmi write`, specifying the target feature, package, instance,
   cluster, register, and bit field.

#### Examples

**List Available TPMI Features**

Here is how to list all available TPMI features on a Granite Rapids system.

```bash
$ pepc tpmi ls
 Supported TPMI features
- rapl (0): Running Average Power Limit (RAPL) reporting and control
- ufs (2): Processor uncore (fabric) monitoring and control
- sst (5): Intel Speed Select Technology (SST) control
- tpmi_info (129): TPMI Info Registers
```

Check the topology of TPMI devices:

```bash
$ pepc tpmi ls --topology
Supported TPMI features
- rapl (0): Running Average Power Limit (RAPL) reporting and control
  - PCI address: 0000:00:03.1
    Package: 0
    Instances: 0
  - PCI address: 0000:80:03.1
    Package: 1
    Instances: 0
- ufs (2): Processor uncore (fabric) monitoring and control
  - PCI address: 0000:00:03.1
    Package: 0
    - Instance: 0
      - Cluster: 0
    - Instance: 1
      - Cluster: 0
... snip ...
```

**Find TPMI Spec Files**

To see which TPMI spec files are available for the target system, use the `--list-specs` option:

```bash
$ pepc tpmi ls --list-specs
TPMI spec directories information:
- /home/dedekind/git/pepc/pepcdata/tpmi
  Format version: 1.0
  VFM: 0x6AD
  Platform Name: Granite Rapids Xeon
  Spec Sub-directory Path: /home/dedekind/git/pepc/pepcdata/tpmi/gnr
TPMI spec files:
- rapl (0): Running Average Power Limit (RAPL) reporting and control
  Spec file: /home/dedekind/git/pepc/pepcdata/tpmi/gnr/rapl.yml
- ufs (2): Processor uncore (fabric) monitoring and control
  Spec file: /home/dedekind/git/pepc/pepcdata/tpmi/gnr/ufs.yml
- sst (5): Intel Speed Select Technology (SST) control
  Spec file: /home/dedekind/git/pepc/pepcdata/tpmi/gnr/sst.yml
- tpmi_info (129): TPMI Info Registers
  Spec file: /home/dedekind/git/pepc/pepcdata/tpmi/gnr/tpmi_info.yml
```

**Read All TPMI Registers**

You can read all TPMI registers of every discovered feature by running `pepc tpmi read` without any
options. However, the output is very long.

To limit the output, use one of the filtering options: '--features', '--addresses', '--packages',
'--instances', '--clusters', '--registers', '--bitfields'.

**Display TPMI Topology**

Use the `--topology` option to see how TPMI devices, packages, and instances are organized:

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

This displays PCI addresses of TPMI devices, their packages, and instance numbers.

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

The output includes cluster information for the UFS feature. UFS is special because instances may
contain multiple clusters, each with its own copy of control registers (like `UFS_STATUS`). Header
registers (`UFS_HEADER` and `UFS_FABRIC_CLUSTER_OFFSET`) appear only once per instance under
cluster 0.

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

The write command output includes cluster information. For UFS, when no cluster is specified, the
command defaults to cluster 0.

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

### TPMI debugfs Dump Decoding

`pepc tpmi` can decode TPMI debugfs dumps captured from other systems. Usage is similar to live
systems, with two key differences:

1. Use `--base` to specify the debugfs dump directory path instead of the default
   '/sys/kernel/debug'.
2. Use `--vfm` to specify the VFM (Vendor, Family, Model) of the source system. This ensures `pepc`
   uses the correct TPMI spec files. If `--vfm` is not provided, `pepc` assumes Granite Rapids Xeon
   (VFM 0x6AD).

**Note:** Currently, only Granite Rapids TPMI spec files are available in the `pepc` git
repository. These files also cover Sierra Forest Xeon, as both platforms share identical TPMI
features and registers. Therefore, specifying `--vfm` is unnecessary unless you have custom spec
files for a different platform.

The debugfs dump directory structure must match the standard TPMI debugfs layout described in the
[Debugfs Interface](#debugfs-interface) section.

All filtering options available for live systems (`--features`, `--packages`, `--instances`,
`--clusters`, `--registers`, `--bitfields`) work the same way with debugfs dumps.

#### Examples

Suppose you have a partial TPMI debugfs dump, that includes only few features:

```
$ tree /home/dedekind/tmp/debugfs-dump/
/home/dedekind/tmp/debugfs-dump/
├── tpmi-0000:00:02.1
│   ├── tpmi-id-00
│   │   └── mem_dump
│   ├── tpmi-id-02
│   │   └── mem_dump
│   ├── tpmi-id-81
│   │   └── mem_dump
│   └── tpmi-id-fe
│       └── mem_dump
└── tpmi-0001:00:02.1
    ├── tpmi-id-00
    │   └── mem_dump
    ├── tpmi-id-02
    │   └── mem_dump
    ├── tpmi-id-81
    │   └── mem_dump
    └── tpmi-id-fe
        └── mem_dump
```

***Check TPMI Spec Files***

It is always handy to first verify that you have the correct TPMI spec files for the target system.
Use the `--list-specs` option along with `--base`. Optionally, use `--vfm` to specify the target
system VFM, but in this example, Granite Rapids Xeon TPMI spec files are OK for decoding.

```bash
$ pepc tpmi ls --list-specs --base /home/dedekind/tmp/debugfs-dump/
pepc: notice: No VFM provided, assuming VFM 0x6AD (Granite Rapids Xeon) for decoding TPMI debugfs dump
TPMI spec directories information:
- /home/dedekind/git/pepc/pepcdata/tpmi
  Format version: 1.0
  VFM: 0x6AD
  Platform Name: Granite Rapids Xeon
  Spec Sub-directory Path: /home/dedekind/git/pepc/pepcdata/tpmi/gnr
TPMI spec files:
- rapl (0): Running Average Power Limit (RAPL) reporting and control
  Spec file: /home/dedekind/git/pepc/pepcdata/tpmi/gnr/rapl.yml
- ufs (2): Processor uncore (fabric) monitoring and control
  Spec file: /home/dedekind/git/pepc/pepcdata/tpmi/gnr/ufs.yml
- sst (5): Intel Speed Select Technology (SST) control
  Spec file: /home/dedekind/git/pepc/pepcdata/tpmi/gnr/sst.yml
- tpmi_info (129): TPMI Info Registers
  Spec file: /home/dedekind/git/pepc/pepcdata/tpmi/gnr/tpmi_info.yml
```

**Read a TPMI Register from the Dump**

To read the 'UFS_STATUS' register of the UFS feature for package 0, instance 0 from the debugfs
dump:

```bash
$ pepc tpmi read -F ufs --registers UFS_STATUS --packages 0 --instances 0 --base /home/dedekind/tmp/debugfs-dump/
pepc: notice: No VFM provided, assuming VFM 0x6AD (Granite Rapids Xeon) for decoding TPMI debugfs dump
- TPMI feature: ufs
  - PCI address: 0000:00:02.1
    Package: 0
  - Instance: 0
    - Cluster: 0
      - UFS_STATUS: 0x18c7f14018c7f14
          CURRENT_RATIO[6:0]: 20
          CURRENT_VOLTAGE[22:7]: 6398
          AGENT_TYPE_CORE[23:23]: 1
          AGENT_TYPE_CACHE[24:24]: 1
          AGENT_TYPE_MEMORY[25:25]: 0
          AGENT_TYPE_IO[26:26]: 0
          RSVD[31:27]: 0
          THROTTLE_COUNTER[63:32]: 25984788
```

**Decode a single 'mem_dump' File**

If you only have the 'mem_dump' file of a specific TPMI feature (e.g., someone sent it to you), you
can decode it too, but you have to create a dummy debugfs dump directory structure first. For
example, if you have only the UFS feature dump file:

```bash
$ mkdir -p ~/tmp/debugfs-dump/tpmi-0000:00:00.1/tpmi-id-02
$ cp mem_dump ~/tmp/debugfs-dump/tpmi-0000:00:00.1/tpmi-id-02/
$ pepc tpmi ls --base ~/tmp/debugfs-dump/
pepc: notice: No VFM provided, assuming VFM 0x6ad (Granite Rapids Xeon) for decoding TPMI debugfs dump
pepc: warning: The 'tpmi_info' feature was not found in the debugfs dump
pepc: notice: Using a dummy 'tpmi_info', assigning package number 0 to TPMI device 0000:00:00.1
Supported TPMI features
- ufs (2): Processor uncore (fabric) monitoring and control
- tpmi_info (129): TPMI Info Registers
```

**Note:** Since the 'tpmi_info' feature is missing in this case, `pepc` creates a dummy 'tpmi_info'
to assign package number 0 to the TPMI device.

And to read all UFS registers from this dump:

```bash
$ pepc tpmi read --base ~/tmp/debugfs-dump/
pepc: notice: No VFM provided, assuming VFM 0x6ad (Granite Rapids Xeon) for decoding TPMI debugfs dump
pepc: warning: The 'tpmi_info' feature was not found in the debugfs dump
pepc: notice: Using a dummy 'tpmi_info', assigning package number 0 to TPMI device 0000:00:00.1
- TPMI feature: tpmi_info
- TPMI feature: ufs
  - PCI address: 0000:00:00.1
    Package: 0
  - Instance: 0
    - Cluster: 0
      - UFS_HEADER: 0x200000102
          INTERFACE_VERSION[7:0]: 2
          LOCAL_FABRIC_CLUSTER_ID_MASK[15:8]: 1
          FLAGS[31:16]: 0
... snip ...
```

#### How To Construct VFM

VFM (Vendor, Family, Model) is a 32-bit value uniquely identifying a CPU model. The encoding is:

```
VFM = (vendor << 16) | (family << 8) | model
```

Where:
- **Vendor codes**: Intel = 0, AMD = 1
- **Family** and **Model**: Obtained from `/proc/cpuinfo`

**Examples**

1. Intel CPU with family 6, model 0xAD (173 decimal):
   ```
   VFM = (6 << 8) | 0xAD = 0x600 | 0xAD = 0x6AD
   ```
2. AMD CPU with family 19, model 0x1:
   ```
   VFM = (1 << 16) | (19 << 8) | 0x1 = 0x10000 | 0x1300 | 0x1 = 0x11301
   ```
