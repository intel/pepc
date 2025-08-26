<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2024-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

* Author: Artem Bityutskiy <dedekind1@gmail.com>
* Date: Aug, 2025

# Table of Contents

- [Introduction](#introduction)
- [Assumptions](#assumptions)
- [How CPU frequency is measured](#how-cpu-frequency-is-measured)
- [CPU frequency and C1](#cpu-frequency-and-c1)
- [CPU frequency and C1E](#cpu-frequency-and-c1e)
- [Idle CPU frequency measurement inaccuracy](#idle-cpu-frequency-measurement-inaccuracy)
- [Conclusions](#conclusions)

# Introduction

Intel Xeon processors support several idle states (C-states), including C1, C1E, and one or
two variants of C6. Each idle state offers a distinct balance between power savings and latency.

* **C1** is the shallowest C-state, providing the least amount of power savings but lowest latency
  (~1μs).
* **C1E** is a deeper C-state, offering more power savings at the cost of increased latency, ~4μs
  on modern Intel Xeon platforms, such as Granite Rapids and Emerald Rapids.
* **C6** and its variants provide substantially greater power savings, but with much higher latency,
  typically > ~100μs. The latency depends on the specific C6 variant and the platform.

Intel Xeon users who have previously relied solely on the C1 idle state may observe changes in CPU
frequency behavior when enabling C1E. Specifically, when the system is profoundly idle,
Linux monitoring tools such as turbostat may report lower CPU frequency than anticipated.

This article aims to clarify the reasons behind this phenomenon, focusing on modern Intel Xeon
platforms, including Sapphire Rapids, Emerald Rapids, Granite Rapids, and Sierra Forest.

# Assumptions

This article assumes that the user has pinned the CPU frequency to a fixed value at or below the
base frequency (we will use 2GHz in the examples). This can be achieved by setting both the minimum
and maximum CPU frequency to the same value for all CPUs via the Linux sysfs interface, or by using
utilities such as 'cpupower' or 'pepc'.

Pinning the CPU frequency eliminates the non-essential complexities introduced by dynamic frequency
scaling, making the analysis more straightforward. However, this simplification does not
fundamentally change the explanations provided in this article.

This article also assumes that the reader has a basic understanding of Linux and Intel CPU idle
states. For an introduction to some of these concepts, please refer to the
[C-state Namespaces](https://github.com/intel/pepc/blob/main/docs/misc-cstate-namespaces.md)
article.

For simplicity, this article uses the terms C1 and C1E to refer to both the requestable C-states
and the corresponding hardware C-states.

# How CPU frequency is measured

Let's begin by exploring how CPU frequency is measured, with a focus on the turbostat utility,
a standard tool available on Linux systems. Turbostat is part of the Linux kernel source tree.
For example, [this link](https://github.com/torvalds/linux/tree/v6.16/tools/power/x86/turbostat)
points to the Linux kernel v6.16 turbostat source code.

At a high level, turbostat periodically wakes up (every 5 seconds by default), captures snapshots of
various counters, computes the difference between consecutive snapshots and reports metrics such as
CPU frequency and C-state residency.

Below is a simplified example of turbostat output.

```
Busy% Bzy_MHz TSC_MHz  IPC  IRQ    NMI SMI POLL%  C1%   C1E%  C6%
24.81 3680    2600     2.41 303428 0   0   0.00   1.00  4.02  70.20
```

The 'Bzy_MHz' metric is the CPU frequency in MHz. The "Bzy_" prefix indicates that this value
reflects the frequency during "busy" periods, when CPU is in C0 (executing instructions), not when
the CPU is in C-state such as C1 or C1E.

The general formula for CPU frequency measurement is:

**F = (Δ apref / Δ mperf) × F_base**, where:

- **F** is the measured CPU frequency in Hz.
- **Δ apref** is the change (delta) in the APERF counter (MSR 0xE8).
- **Δ mperf** is the change (delta) in the MPERF counter (MSR 0xE7).
- **F_base** is the base frequency of the CPU in Hz.

The APERF counter increments every CPU cycle when the CPU is in C0 state. The rate of increments
follows the CPU frequency. For example, if CPU frequency increases from 1GHz to 2GHz, APERF
increments twice as fast.

The MPERF counter also increments every CPU cycle only when the CPU is in the C0 state, but unlike
APERF, its increment rate is tied to the base CPU frequency. This means that regardless of the
actual CPU frequency, MPERF always increases at a constant rate determined by the processor’s base
frequency.

Both APERF and MPERF counters increment only while the CPU is in C0. When the processor enters a
C-state, these counters stop incrementing until the CPU exits the C-state and returns to C0.

# CPU frequency and C1

When a CPU exits C1, its frequency is the same as the frequency it was running at before entering
C1. For example, if CPU is running at 2GHz, then enters C1, it will run at 2GHz when it exits C1.

The hardware CC1 state (corresponds to requestable C1) is essentially a clock-gating mechanism: the
CPU clock is disabled to reduce dynamic power, while the voltage remains unchanged. Upon exiting
CC1, the clock is re-enabled and the CPU resumes at its previous frequency.

As a result, entering or exiting C1 has no effect on the CPU frequency reported by monitoring tools
such as turbostat. The measured "busy" frequency remains at 2GHz, regardless of whether the CPU
transitions through C1.

But keep in mind, when measuring a profoundly idle system, the reported CPU frequency may be
noticeably inaccurate due to limitations in the measurement algorithm. This phenomenon will be
explained in a later section.

# CPU frequency and C1E

When a CPU exits C1E, its frequency may be for a short time below the value it was running at before
entering C1E.

For example, if the CPU was operating at 2GHz and then entered C1E, it might resume at 1.5GHz upon
exit. The frequency will then ramp back up to 2GHz while the CPU is already executing instructions.

The hardware CC1E state (corresponding to requestable C1E) combines clock-gating with voltage
and frequency scaling. By lowering the CPU voltage in CC1E, the processor achieves additional
leakage power savings on top of the dynamic power reduction provided by CC1.

Consequently, monitoring tools such as turbostat may report a lower-than-expected CPU frequency when
the C1E is enabled. For instance, turbostat may report 1.9GHz instead of the expected 2GHz.

But in practice, the CPU ramps its frequency back up so rapidly that the lower frequency is only
observed on profoundly idle systems, where the CPU spends little time in C0 and frequently
transitions between C0 and C1E. For instance, if the CPU is 5–10% busy, turbostat will report
2GHz, and the C1E-related transient frequency ramps will be indistinguishable from measurement
noise.

# Idle CPU frequency measurement inaccuracy

The APERF and MPERF counters are two separate MSRs, which means that they are read one after
another, and there is always a time interval between APERF and MPERF read operations.

Depending on system configuration, turbostat reads APERF and MPERF either through the Linux kernel
MSR driver ('/dev/cpu/cpu*/msr') or via the perf subsystem. When using the MSR driver, APERF and
MPERF are read with two separate syscalls. When using Linux perf subsystem, turbostat can read both
counters in a single syscall by leveraging perf's event grouping feature.

When using the MSR driver, there is a longer time gap between reading APERF and MPERF compared to
using the perf subsystem.

On profoundly idle systems, the changes in APERF and MPERF counters (Δ apref and Δ mperf) during the
measurement interval can be similar in magnitude to the time gap between reading APERF and MPERF.
This can introduce substantial inaccuracies in the reported busy CPU frequency.

# Conclusions

1. When C1E is enabled and the system is less than 3-5% busy, Linux tools like turbostat may report
   lower-than-expected CPU frequencies due to the short, transient frequency ramps associated with
   C1E.
1. When C1E is enabled and the system is 5-10% busy, the reported CPU frequency aligns with the
   expected value, as the transient effects of C1E become negligible.
1. On systems that are profoundly idle, CPU frequency measurements may be inaccurate due to
   increased measurement errors.

Finally, the author of this article considers the practice of measuring CPU frequency on a
profoundly idle system to be of limited value and potentially misleading.
