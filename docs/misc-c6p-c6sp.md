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
- [C6](#c6)
  - [C6S](#c6s)
- [The problem](#the-problem)
- [C6P](#c6p)

# Introduction

Intel Xeon platforms have long offered C6 as the deepest requestable C-state. In 2025, the
Granite Rapids Xeon platform introduced C6P, and the Sierra Forest Xeon platform introduced C6SP.

To understand this description of C6P and C6SP, the reader should first be familiar with the concept
of requestable C-state and hardware C-state, which are described here in
[C-state Namespaces](https://github.com/intel/pepc/blob/main/docs/misc-cstate-namespaces.md).

Note that this article comprehends Intel server platforms through 2025, but may need to be further
updated for future platforms.

# C6

The C6 state has been the deepest requestable C-state on Intel server platforms prior to 2025.
This includes Emerald Rapids Xeon and on earlier server platforms, such as Sapphire Rapids, Ice
Lake, Cooper Lake, Cascade Lake, Skylake Xeons.

When the OS requests C6 on a core, the core may enter one of the following hardware C-states:

* **Core C1, aka CC1**: The CPU may spend some time in CC1 prior to entering CC6, for example due to
  C1 demotion feature. The precise behavior depends on the platform and platform configuration, but
  the general idea is to keep the CPU in CC1 when it is likely to be woken up again soon. The CPU
  may be promoted to CC6 after spending enough time in CC1.
* **Core C6, aka CC6**: The deepest core-level hardware C-state, where the core is powered off.
  Before power-gating the core, the platform saves the core state (such as registers), restoring it
  upon wake-up.
* **Package C6, aka PC6**: Package C6 has global system scope on Intel Xeons.  It is entered only
  when all CPUs across all sockets (packages) have transitioned to CC6. PC6 is entered only when the
  system is profoundly idle and offers maximum power savings by putting some global components, such
  as the memory controller, interconnects and shared caches into a low power state.

Hardware will never enter a C-state deeper than the OS request. Hardware is free to "demote" to
states shallower than the OS request. If the hardware later changes its mind about demoting, it can
"un-demote", but will never promote to a request deeper than the OS request. In this way, the OS and
the hardware work together to choose C-states with minimal performance impact.

**Note on Hyper-Threading**: Hardware coordinates C-states requests by SMT siblings, choosing the
shallowest for the core. For instance, if one logical CPU requests C1 and the other requests C6, the
core chooses the shallowest - CC1. This hardware coordination is transparent to software, and so SMT
is omitted from the discussion below.

**DMA latency implications**: CC6 impacts interrupt latency, but does not shut down the path between
IO and memory, so it does not impact DMA latency. PC6 is a super-set of CC6, to save more energy than
CC6. It does turn off the path between IO and memory, so it does impact DMA latency. For example, if
a PCIe Network Card receives a packet and attempts to transfer it from its internal memory to main
memory, it will encounter a delay while waiting for the memory controller to exit the low power
state. But when the Network Card generates an interrupt for the received packet, both CC6 and PC6
will incur interrupt latency (although lower with CC6). So while CC6 does not affect DMA latency,
it does impact interrupt latency.

## C6S

The C6S requestable C-state is essentially an alternative name for C6, used on Intel platforms
featuring a shared L2 cache architecture. For instance, on Sierra Forest Xeon processors, the L2
cache is shared between four cores, while on Granite Rapids Xeon each core has a dedicated L2.

The "S" stands for "Shrink", indicating that the L2 cache is flushed ("shrunk") as part of entering
the Module C6 state.

For the purposes of this article, there is no significant difference between C6 and C6S. Therefore,
the discussion will focus on C6.

# The problem

The issue with C6 is that it encompasses hardware C-states with significantly different
characteristics:
* **CC6**: Lower exit latency compared to PC6 (e.g., ~200µs at 99.99th precentile on Sapphire
  Rapids Xeon) and no impact on DMA latency.
* **PC6**: Higher exit latency (e.g., ~300µs at 99.99th percentile on Sapphire Rapids Xeon) and
  significantly increased DMA latency. Lower power comparing to CC6.

The OS cannot distinguish between these two hardware C-states when it requests C6, and it has no way
to express a preference for one over the other. The Linux intel_idle driver addresses the problem by
assuming the "worst case" situation, which means it treats C6 as if it always results in PC6.

Whenever a CPU becomes idle, Linux selects which C-state to request based on characteristics such as
exit latency and target residency. For example, if an application on Sapphire Rapids sets a maximum
latency tolerance of 200µs using the Linux Power Management Quality of Service (PM QoS) API, Linux
will avoid requesting C6. As a result, cores will not enter CC6, even though CC6’s exit latency is
within the specified limit.

If a Linux user finds the exit latency of CC6 acceptable but cannot tolerate the increased DMA
latency caused by PC6, their only option is to disable C6 entirely. This action disables both CC6
and PC6, preventing the system from benefiting from the energy savings provided by CC6 that
is not subject to the latency cost of PC6.

**Note on MSR 0xE2**: Intel Xeon platforms allow disabling PC6 via the BIOS or the
MSR_PKG_CST_CONFIG_CONTROL (0xE2) model-specific register. However, this is effectively a boot-time
setting and cannot be changed dynamically by the Linux kernel or user space applications. While this
approach helps some users, it does not offer a general solution, particularly since many Linux
systems disable MSR access for security reasons.

# C6P

In Granite Rapids Xeon, the original C6 requestable C-state was split into two distinct requestable
C-states: C6 and C6P (similarly, Sierra Forest Xeon's C6S was split into C6S and C6SP).

On Granite Rapids Xeon:

* **C6 requestable C-state**: may result in CC1 or CC6, but *not* PC6. This means it behaves like C6
  on previous generations, except it prevents entry into PC6.
* **C6P requestable C-state**: may result in CC1, CC6, or PC6. This is functionally equivalent to
  the original C6 behavior on earlier platforms.

On Granite Rapids Xeon, the Linux kernel can differentiate between the C6 and C6P requestable
C-states when choosing which C-state to enter. Based on the predicted idle duration and the latency
tolerance requirements, Linux selects the most appropriate C-state, allowing for more precise
control over power savings and latency trade-offs.

If the latency impact of PC6 is undesirable, users or user-space applications can prevent entry into
PC6, while still allowing CC6 by disabling C6P through the sysfs or PM QoS interfaces. This can be
done at runtime, without requiring a reboot, and C6P can be re-enabled at any time, if needed.
