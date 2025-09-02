<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2024-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

* Author: Artem Bityutskiy <dedekind1@gmail.com>
* Date: Sep, 2025

# Table of Contents

- [Introduction](#introduction)
- [Terminology](#terminology)
- [UFS Overview](#ufs-overview)
  - [Idle latency](#idle-latency)
  - [All out performance mode](#all-out-performance-mode)
- [ELC Overview](#elc-overview)
- [pepc uncore control](#pepc-uncore-control)
- [Examples](#examples)
  - [Display all uncore properties](#display-all-uncore-properties)
  - [Measure idle system](#measure-idle-system)
  - [Measure busy system](#measure-busy-system)
- [Pepc mechanisms](#pepc-mechanisms)
  - [TPMI mechanism](#tpmi-mechanism)

# Introduction

Uncore Frequency Scaling (UFS) is Intel processors' algorithm that automatically adjusts uncore
frequency based on workload demands, similar to how core frequencies scale with CPU load level.

Efficiency Latency Control (ELC) is a UFS feature introduced in the newest Intel Granite Rapids and
Sierra Forest Xeon platforms, aimed at providing customers a configurable trade-off between
processor energy efficiency, performance, and latency.

This article summarizes UFS, ELC and describes relevant 'pepc' tool command-line options. It focuses
on Intel Granite Rapids and Sierra Forest server platforms. Future platforms may require an update
to this article.

# Terminology

- **Uncore**: Processor components excluding the cores themselves, such as the inter-core fabric,
  memory controllers, last-level cache (LLC), and PCIe/CXL controllers.
- **Uncore Frequency Scaling (UFS)**: Intel's algorithm for dynamically adjusting uncore frequency
  based on workload demands.
- **Efficiency Latency Control (ELC)**: A UFS feature for configurable trade-offs between energy
  efficiency, performance, and latency.
- **Thermal Design Power (TDP)**: The maximum amount of power the processor is allowed to consume.

# UFS Overview

A substantial portion of processor power is consumed by the uncore components. UFS aims to optimize
the performance and power efficiency of the processor by dynamically adjusting uncore frequency
based on real-time workload demands. This allows the processor to deliver higher performance when
needed while conserving energy during periods of lower activity.

On Granite Rapids and Sierra Forest Xeon platforms, UFS manages uncore frequency on a per-die basis.
Each socket typically contains 2–3 compute dies (with cores) and 2 I/O dies (with components like
PCIe controllers). Uncore frequency is controlled individually for each die.

At a high level, UFS operates by continuously monitoring the overall utilization of each die,
including both core activity and uncore component usage, such as the die fabric traffic volume.
Based on this aggregated utilization, the processor dynamically adjusts the uncore frequency.
However, the adjustments are subject to constraints such as TDP, thermal limits, etc.

## Idle latency

When aggregate die utilization is low, UFS reduces uncore frequency, which saves energy, but
increases latency. If, for example, the workload has many activity spikes, the processor may
not be able to ramp up uncore frequency quickly enough, due to the reactive nature of the UFS
algorithm. ELC low threshold (described below) helps to address this potential issue.

## All out performance mode

In certain scenarios, die utilization may be high, but not high enough for the UFS algorithm to
select the highest uncore frequency. Some customers may prefer the processor to enter the "all out"
performance mode sooner, maximizing performance even at moderate die utilization levels. The ELC
high threshold (described below) enables this behavior.

# ELC Overview

ELC enhances UFS by introducing **ELC Low Threshold** and **ELC High Threshold** user-configurable
thresholds. These thresholds represent aggregate die utilization percentages, with the low threshold
less than or equal to the high threshold.

The thresholds define three per-die ELC zones:
1. **ELC Low Zone**: Aggregate die utilization is within (0%, low threshold].
1. **ELC Middle Zone**: Aggregate die utilization is within (low threshold, high threshold).
1. **ELC High Zone**: Aggregate die utilization is within [high threshold, 100%].

ELC also introduces two user-configurable minimum uncore frequency settings:
1. **ELC Low Zone Minimum Uncore Frequency**: Specifies the lowest allowed uncore frequency (in Hz)
   when the die is operating in the ELC low zone.
1. **ELC Middle Zone Minimum Uncore Frequency**: Specifies the lowest allowed uncore frequency (in Hz)
   when the die is operating in the ELC middle zone.

The ELC low and middle zone minimum uncore frequencies provide a way to ensure that even under low
or moderate utilization, the uncore components still operate at the minimum required frequency
(which is workload and user-specific).

There is no ELC high zone minimum uncore frequency, though, because the primary goal at the ELC high
zone is to maximize performance. Instead, when a die enters the ELC high zone, UFS automatically
increases the uncore frequency as much as possible, subject to platform constraints such as TDP and
thermal limits. The actual frequency achieved depends on workload characteristics and available
power headroom. But the aim is to utilize any remaining TDP capacity to boost uncore performance.

Additionally, users can disable the ELC high threshold via a dedicated knob. When it is disabled,
the processor reverts to the standard UFS algorithm in this zone, rather than boosting the uncore
frequency.

Note that the UFS frequency control range is always constrained by the user-configurable global UFS
uncore frequency limits. For instance, if the global minimum uncore frequency is set to 2GHz, but
the ELC low and middle zone minimum uncore frequencies are configured to 1GHz, the effective minimum
uncore frequency in both ELC low and middle zones will be 2GHz (subject to TDP/thermal and other
constraints, though).

# pepc uncore control

The 'pepc' tool offers command-line options to view and configure UFS parameters using the 'pepc
uncore info' and 'pepc uncore config' commands.

To display the platform's supported minimum and maximum uncore frequencies, run:

```
pepc uncore info --min-freq-limit --max-freq-limit
```

To set the global minimum and maximum uncore frequencies, use:

```
pepc uncore config --min-freq <value> --max-freq <value>
```

To enable or disable the ELC high threshold feature:

```
pepc uncore config --elc-high-threshold-status <on|off>
```

To adjust the ELC low and high threshold percentages:

```
pepc uncore config --elc-low-threshold <percentage> --elc-high-threshold <percentage>
```

To configure the minimum uncore frequency for the ELC low and middle zones:

```
pepc uncore config --elc-low-zone-min-freq <value> --elc-mid-zone-min-freq <value>
```

For more details, refer to the
[manual page](https://github.com/intel/pepc/blob/main/docs/pepc-uncore.rst).

# Examples

## Display all uncore properties

Let's take a 2-socket Granite Rapids Xeon (GNR) server as an example and display all available
uncore properties:

```
$ pepc uncore info
Source: Linux sysfs file-system
 - Min. uncore frequency: 800.00MHz for all dies in all packages
 - Max. uncore frequency: 2.20GHz for dies 0,1 in package 0, dies 0,1 in package 1
 - Max. uncore frequency: 2.50GHz for dies 3,4 in package 0, dies 3,4 in package 1
 - Min. supported uncore frequency: 800.00MHz for all dies in all packages
 - Max. supported uncore frequency: 2.20GHz for dies 0,1 in package 0, dies 0,1 in package 1
 - Max. supported uncore frequency: 2.50GHz for dies 3,4 in package 0, dies 3,4 in package 1
 - ELC low zone min. uncore frequency: 1.20GHz for dies 0,1 in package 0, dies 0,1 in package 1
 - ELC low zone min. uncore frequency: 800.00MHz for dies 3,4 in package 0, dies 3,4 in package 1
 - ELC low threshold: 11% for all dies in all packages
 - ELC high threshold: 95% for all dies in all packages
 - ELC high threshold status: 'on' for all dies in all packages
Source: Topology Aware Register and PM Capsule Interface (TPMI)
 - ELC middle zone min. uncore frequency: 1.20GHz for dies 0,1 in package 0, dies 0,1 in package 1
 - ELC middle zone min. uncore frequency: 800.00MHz for dies 3,4 in package 0, dies 3,4 in package 1
 ```

The hardware supports a minimum uncore frequency of 800MHz. The maximum uncore frequency depends on
the die type: compute dies support up to 2.2GHz, while I/O dies support up to 2.5GHz. Side note: to
identify which dies are compute or I/O, use the 'pepc topology info' command.

The current global uncore frequency limits are set to the hardware-supported minimum and maximum:
800MHz and 2.2GHz, respectively.

The ELC low threshold is 11%, and ELC high threshold is 95%. ELC low and middle zone minimum uncore
frequency is 1.2GHz for compute dies, and 800MHz for I/O dies.

## Measure idle system

Let's run tubostat on idle system and observe the uncore frequency.

```
$ turbostat -q -S --hide all --show frequency
Avg_MHz Busy% Bzy_MHz TSC_MHz UMHz0.0 UMHz1.0 UMHz3.0 UMHz4.0
0       0.03  849     2601    1200    1200    800     800
0       0.03  801     2600    1200    1200    800     800
0       0.05  800     2600    1200    1200    800     800
```

As expected, the idle system operates within the ELC low zone, so the ELC low zone minimum uncore
frequency is enforced: 1.2GHz for compute dies (shown as UMHz0.0 and UMHz1.0 in turbostat), and
800MHz for I/O dies (UMHz3.0 and UMHz4.0).

Let's raise the global minimum uncore frequency to 1.5GHz for compute dies and 1GHz for I/O dies.

```
$ pepc uncore config --min-freq 1.5GHz --packages 0,1 --dies 0,1
Min. uncore frequency: set to 1.50GHz for dies 0,1 in package 0, dies 0,1 in package 1

$ pepc uncore config --min-freq 1GHz --packages 0,1 --dies 3,4
Min. uncore frequency: set to 1.00GHz for dies 3,4 in package 0, dies 3,4 in package 1
```

Rerun turbostat:

```
$ turbostat -q -S --hide all --show frequency
Avg_MHz Busy% Bzy_MHz TSC_MHz UMHz0.0 UMHz1.0 UMHz3.0 UMHz4.0
0       0.03  841     2602    1500    1500    1000    1000
0       0.03  799     2600    1500    1500    1000    1000
```

The observed uncore frequencies reflect the updated global minimum settings, demonstrating that the
global minimum frequency overrides the ELC low zone minimum frequency for compute dies.

## Measure busy system

Let's run a CPU stress test to simulate a 70% busy system and observe the uncore frequency behavior.

```
$ stress-ng --cpu $(nproc) --cpu-load 70 --timeout 3600 --cpu-method bitops
```

And measure the system with turbostat:

```
Avg_MHz Busy% Bzy_MHz TSC_MHz UMHz0.0 UMHz1.0 UMHz3.0 UMHz4.0
2670    71.51 3738    2597    1850    1850    1750    1750
2670    71.43 3738    2600    1850    1850    1750    1750
```

UFS increased the uncore frequency to 1.85GHz for compute dies and 1.75GHz for I/O dies, based on
die utilization.

Let's enable the ELC high threshold and set it to 50%. This ensures the processor enters the ELC
high zone.

```
$ pepc uncore config --elc-high-threshold-status on --elc-high-threshold 50%
ELC high threshold status: set to 'on' for all dies in all packages
ELC high threshold: set to 50% for all dies in all packages
```

And rerun turbostat:

```
Avg_MHz Busy% Bzy_MHz TSC_MHz UMHz0.0 UMHz1.0 UMHz3.0 UMHz4.0
2660    71.18 3736    2600    2200    2200    2500    2500
2659    71.17 3738    2598    2200    2200    2500    2500
```

The turbostat output shows that the uncore frequency for all dies was boosted to the maximum
possible value.

# Pepc mechanisms

The 'pepc' tool provides two mechanisms for reading and writing UFS and ELC properties: '**sysfs**'
and '**tpmi**'. By default, 'pepc' first attempts to use the sysfs interface. If sysfs is
unavailable (for example, if the uncore Linux kernel driver is not loaded), 'pepc' automatically
falls back to TPMI.

The 'sysfs' mechanism uses the Linux sysfs interface to read and write uncore properties. For
example, the '--elc-low-zone-min-freq' option corresponds to the following sysfs path:
'/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/elc_floor_freq_khz'.

When users specify package and die numbers using the '--packages' and '--dies' options, 'pepc'
automatically maps them to the corresponding uncore frequency domain number ("<NUMBER>") in the
sysfs path.

The 'tpmi' mechanism utilizes the TPMI (Topology Aware Register and PM Capsule Interface) hardware
interface to access and modify uncore properties. TPMI is Intel's standardized solution for exposing
power management and other registers to software, replacing the legacy MSR-based methods.

Here are example commands for selecting the mechanism used by 'pepc' to change uncore properties.

```
# Try the 'tpmi' mechanism first; if unavailable, fall back to 'sysfs'.
pepc uncore config --elc-high-threshold-status off --mechanisms tpmi,sysfs

# Use only the 'tpmi' mechanism (do not fall back to 'sysfs').
pepc uncore config --elc-high-threshold-status off --mechanisms tpmi
```

Note: the '--elc-mid-zone-min-freq' option is supported only when using the 'tpmi' mechanism, as the
Linux kernel uncore driver does not provide a sysfs interface for this property.

## TPMI mechanism

On Linux systems, TPMI devices are enumerated as PCIe devices using standard procedures. The Linux
TPMI driver maps the MMIO regions of these TPMI PCIe devices into kernel memory and makes them
accessible to user space via the Linux debugfs file system.

The TPMI mechanism offers two key benefits:
1. Uncore properties remain accessible even when the Linux uncore kernel driver is disabled.
2. It enables direct access to TPMI registers that are not exposed by the Linux kernel (check out
   the 'pepc tpmi' command).

However, in the current implementation, 'pepc' relies on both the debugfs file system and the TPMI
kernel driver. On some Linux systems, debugfs may be disabled or the TPMI kernel driver may not be
loaded. In these cases, the 'tpmi' mechanism in 'pepc' will not function.

An alternative approach for implementing the 'tpmi' mechanism could involve mapping the TPMI
device's MMIO regions directly into user space, removing the need for the Linux kernel driver and
debugfs. The 'pepc' tool author did not investigate this method, but in theory it could be a viable
solution if kernel support is unavailable.
