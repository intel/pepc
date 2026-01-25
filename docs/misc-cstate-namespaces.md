<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# C-state Namespaces

- Author: Artem Bityutskiy \<dedekind1@gmail.com\>
- Date: May, 2025

## Table of Contents

- [Introduction](#introduction)
- [Requestable C-states](#requestable-c-states)
- [Hardware C-states](#hardware-c-states)
  - [Hardware C-states scope](#hardware-c-states-scope)
- [ACPI C-states](#acpi-c-states)
- [Linux Names](#linux-names)
  - [Example: ACPI Mode](#example-acpi-mode)
  - [Example: Native Mode](#example-native-mode)

## Introduction

A C-state is a CPU idle power state. When Linux has no tasks to schedule on a CPU, it requests a
C-state. In this state, the CPU halts instruction execution, waits for an event, and conserves power.
Upon an event, the CPU exits the C-state and resumes executing instructions.

This document discusses C-states on Intel platforms and focuses on classifying C-states based on
their "namespaces".

## Requestable C-states

Requestable C-states are C-states that Linux requests using the 'MWAIT' CPU instruction.
The 'MWAIT' instruction takes a "hint" argument, specifying the desired C-state for the CPU.
For instance, 'MWAIT 0x0' requests C1, while 'MWAIT 0x20' requests C6.

For example, for Intel Sierra Forest (SRF), the requestable C-states are:

- C1 - MWAIT 0x0
- C1E - MWAIT 0x1
- C6S - MWAIT 0x22
- C6SP - MWAIT 0x23

For Intel Granite Rapids (GNR), the requestable C-states are:

- C1 - MWAIT 0x0
- C1E - MWAIT 0x1
- C6 - MWAIT 0x20
- C6P - MWAIT 0x21

These C-states range from the shallowest, C1, which offers lower power savings but minimal latency,
to the deepest, C6P, which provides maximum power savings at the cost of higher latency.

Notes:
- In some configurations, such as when the `cpuidle` subsystem is disabled, Linux uses the HLT
  instruction to enter an idle state on Intel CPUs. The HLT instruction typically corresponds to the
  hardware CC1 C-state.
- Linux supports a POLL idle state, implemented as a loop that includes NOP instructions. Unlike other
  C-states, POLL has no corresponding hardware C-state, and in the POLL state the CPU continues
  executing instructions without halting.

## Hardware C-states

Hardware C-states represent the power-saving states supported by the processor, varying by product.

Linux is unaware of hardware C-states and the complex conditions required for entering them. It only
manages requestable C-states, each corresponding to the deepest permissible hardware C-state. For
example, on the Intel Granite Rapids Xeon platform, the mapping is as follows:

- C1 → CC1: Requestable C1 maps to hardware Core C1.
- C1E → CC1E: Requestable C1E maps to hardware Core C1E.
- C6 → CC6: Requestable C6 maps to hardware Core C6.
- C6P → PC6: Requestable C6P maps to hardware Package C6.

When Linux requests a C-state, the hardware may enter any shallower C-state but not a deeper one.
For instance, if the OS requests C6, the hardware can keep the core in CC1 but cannot enter PC6.
If Linux requests C6P, the hardware can keep the core in CC6, and enter PC6 only when all other
cores have entered CC6.

The hardware may choose a shallower C-state than requested for various reasons, such as:
- A deeper C-state is blocked, e.g., an active core prevents entering PC6.
- CPU power management features like C1 demotion prioritize keeping the core in CC1 over entering
  CC6.

There may be more hardware C-states than requestable C-states. For example, SRF MC6 is a hardware
C-state entered when all four cores in a module request C6S or C6SP. If some cores in the module
request C6S while others remain in C0 or request C1/C1E, the module will not enter MC6. In short,
requesting C6S on an SRF core may result in the core entering CC1 or CC6/MC6, depending on
conditions.

The SRF requestable-to-hardware C-states mapping is as follows:

| Requestable | Hardware           |
| ----------- | ------------------ |
| C1          | CC1                |
| C1E         | CC1, PC1E          |
| C6S         | CC1, CC6, MC6      |
| C6SP        | CC1, CC6, MC6, PC6 |

### Hardware C-states scope

Linux requests C-states on a per-CPU basis, selecting the C-state independently for each CPU without
coordination with others. Thus, from Linux's perspective, requestable C-states are scoped to individual
CPUs.

Hardware C-states, however, have scope. Here are some of the hardware C-state scopes.

- **Core scope**: A core consists of one or more execution units and an L1 cache. Hardware C-state
  power-saving actions, such as clock-gating, voltage reduction, or power-gating, apply to a single
  core. Examples include CC1 and CC6.
- **Module scope**: A module includes multiple cores and a shared L2 cache, as on the SRF platform.
  Module-wide power-saving actions, such as lowering L2 cache voltage, occur when all cores in the
  module enter a required core hardware C-state. For instance, on SRF, MC6 (module C6) is triggered
  when all cores enter CC6. This happens when the OS requests C6S or C6SP on all module cores.
- **Package scope**: A package includes multiple cores/modules, the L3 cache, and components like
  memory controllers, I/O controllers, and interconnects. Package-wide power actions, such as
  clock-gating the interconnect or lowering L3 voltage, occur when all cores/modules in the package
  enter a required hardware C-state. These actions are platform- and vendor-specific, often
  configurable via BIOS. For example, on Intel Granite Rapids, PC6 may be triggered when OS requests
  C6P on all cores, all cores enter CC6, and no interconnect traffic exists (e.g., a PCIe NIC is not
  transferring data to main memory via DMA).

## ACPI C-states

The ACPI standard introduces a distinct C-state namespace, defining three states: C1, C2, and C3.
On Intel platforms, the BIOS exposes these states through ACPI _CST tables and typically maps
ACPI C1 to requestable C1 or C1E, and ACPI C2/C3 to deeper requestable C-states.

Here is an example of an Intel Sierra Forest configuration.

| ACPI C-state| Requestable C-state | Possible Hardware C-state |
|-------------|---------------------|---------------------------|
| C1          | C1E                 |  CC1, PC1E                |
| C2          | C6SP                |  CC1, CC6, MC6, PC6       |

## Linux Names

On Intel platforms, Linux exposes either requestable or ACPI C-state names to users,
depending on the idle driver:

- **intel_idle (native mode):** Uses built-in, platform-specific C-states tables to determine
  requestable C-states. Exposes the names of these requestable C-states to user-space.
- **intel_idle (ACPI mode):** Uses C-states defined in the ACPI \_CST table. Exposes these C-states
  to user-space with an "ACPI_" prefix added to their names.
- **acpi_idle:** Uses C-states from the ACPI \_CST table. Exposes the ACPI-defined names to users.

Here is an example for the Intel Sierra Forest platform.

- **intel_idle (native mode):** User-visible C-states: C1, C1E, C6S, C6SP.
- **intel_idle (ACPI mode):** User-visible C-states: C1_ACPI, C2_ACPI, or C3_ACPI (only one).
  - C1_ACPI maps to either C1 or C1E, depending on BIOS settings.
  - C2_ACPI/C3_ACPI map to C6S or C6SP, depending on BIOS settings.
- **acpi_idle:** User-visible C-states: C1, C2, or C3 (only one).
  - C1 maps to either C1 or C1E, depending on BIOS settings.
  - C2/C3 map to C6S or C6SP, depending on BIOS settings.

### Example: ACPI Mode

Here is `pepc` output on an Intel Granite Rapids platform using the `intel_idle` driver in ACPI mode
(in practice, an older kernel that does not include
[commit 370406bf5738dade8ac95a2ee95c29299d4ac902](https://github.com/torvalds/linux/commit/370406bf5738dade8ac95a2ee95c29299d4ac902)
and
[commit 4c411cca33cf1c21946b710b2eb59aca9f646703](https://github.com/torvalds/linux/commit/4c411cca33cf1c21946b710b2eb59aca9f646703)).
The C1E autopromotion feature is enabled in the BIOS, and the package C-state limit is set to PC0 in
the BIOS settings.

```bash
$ pepc cstates info
Source: Linux sysfs file-system
- POLL: 'on' for all CPUs
    - description: CPUIDLE CORE POLL IDLE
    - expected latency: 0 us
    - target residency: 0 us
- C1_ACPI: 'on' for all CPUs
    - description: ACPI FFH MWAIT 0x0
    - expected latency: 1 us
    - target residency: 1 us
- C2_ACPI: 'on' for all CPUs
    - description: ACPI FFH MWAIT 0x21
    - expected latency: 210 us
    - target residency: 630 us
Source: Model Specific Register (MSR)
- Package C-state limit: 'PC0' for all packages
- C1E autopromote: 'on' for all packages
... snip ...
```

There are 2 idle states (excluding POLL).
- **C1_ACPI**: Mapped to the requestable C1 (MWAIT 0x0). However, due to the "C1 autopromote"
  feature being enabled, the platform re-maps all C1 requests to C1E requests. Therefore,
  effectively, C1_ACPI is mapped to the requestable C1E.
- **C2_ACPI**: Mapped to the requestable C6P (MWAIT 0x21). However, since the package C-state limit
  is set to PC0, PC6 is disabled. As a result, the deepest hardware C-state for C6P will be CC6
  (core C6).

### Example: Native Mode

Here is `pepc` output on an Intel Granite Rapids platform using the `intel_idle` driver in native
mode. The C1E autopromotion feature is enabled in the BIOS, and the package C-state limit is set to
PC6 in the BIOS settings.

```bash
$ pepc cstates info
Source: Linux sysfs file-system
- POLL: 'on' for all CPUs
  - description: CPUIDLE CORE POLL IDLE
  - expected latency: 0 us
  - target residency: 0 us
- C1: 'on' for all CPUs
  - description: MWAIT 0x00
  - expected latency: 1 us
  - target residency: 1 us
- C1E: 'on' for all CPUs
  - description: MWAIT 0x01
  - expected latency: 4 us
  - target residency: 4 us
- C6: 'on' for all CPUs
  - description: MWAIT 0x20
  - expected latency: 170 us
  - target residency: 650 us
- C6P: 'on' for all CPUs
  - description: MWAIT 0x21
  - expected latency: 210 us
  - target residency: 1000 us
Source: Model Specific Register (MSR)
- Package C-state limit: 'PC6' for all packages
- C1E autopromote: 'off' for all packages
... snip ...
```

There are 4 idle states (excluding POLL):
- **C1**: Mapped to requestable C1. The deepest hardware C-state is CC1. The `intel_idle` driver in
  native mode disables C1E autopromotion, so it does not matter if it is enabled in the BIOS or not.
- **C1E**: Mapped to requestable C1E. The deepest hardware C-state is CC1E.
- **C6**: Mapped to requestable C6. The deepest hardware C-state is CC6.
- **C6P**: Mapped to requestable C6P. The deepest hardware C-state is PC6.
