<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2024-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

* Author: Artem Bityutskiy <dedekind1@gmail.com>
* Date: May, 2025

# Table of contents

- [Table of contents](#table-of-contents)
- [Introduction](#introduction)
- [Functional Scope](#functional-scope)
- [Scope: platform-dependent](#scope-platform-dependent)
- [Scope: per-bit field](#scope-per-bit-field)
- [I/O Scope](#io-scope)
  - [Example Platform](#example-platform)
  - [Introduction](#introduction-1)
  - [Mental model](#mental-model)
- [MSR_PKG_CST_CONFIG_CONTROL](#msr_pkg_cst_config_control)
  - [Example](#example)
  - [Initial configuration](#initial-configuration)
  - [Topology](#topology)
  - [Confusing configuration](#confusing-configuration)
  - [Enable PC6](#enable-pc6)
  - [Verify PC6](#verify-pc6)
  - [More confusing configuration](#more-confusing-configuration)
  - [Clarify the situation](#clarify-the-situation)

# Introduction

This article discusses MSR (Model Specific Register) scope, which can occasionally be nuanced.
Understanding MSR scope is important when dealing with some of the Power Management MSRs on Intel
platforms.

Intel CPUs support many Model Specific Registers (MSRs), enabling the operating system to control or
monitor various CPU features and metrics. For instance, MSR_HWP_REQUEST (0x774) allows reading or
setting CPU's Energy Performance Preference (EPP). EPP serves as a hint to the hardware on whether
to prioritize energy efficiency or performance.

Intel CPUs provide special instructions for reading and writing MSRs: 'RDMSR' and 'WRMSR'. Some MSRs
are architectural, meaning they are supported across multiple CPU models and are expected to remain
available in future products. These MSRs typically have names starting with 'IA32_'.

Some MSRs are non-architectural. There is no guarantee that these MSRs will be supported on all
platforms, as they may be removed or altered in future products.

# Functional Scope

When discussing the scope of an MSR, the term typically refers to its functional scope. This defines
the level at which the register operates: CPU, core, module, die, or package.

For instance, MSR_HWP_REQUEST (0x774) operates at the CPU scope. If CPU A modifies the EPP value
(bits 31-24), the change will impact only CPU A. The EPP value for CPU B will remain unaffected.

Another example is MSR_PKG_POWER_LIMIT (0x610), which operates at the package scope. If CPU A and
CPU B reside within the same package, any changes made to this MSR by CPU A will also affect CPU B.
However, if CPU C belongs to a different package, the changes made by CPU A will not impact CPU C.

For many MSRs, the scope story ends there. However, certain non-architectural MSRs introduce
additional complexities:
1. The scope can vary depending on the platform.
2. The scope may not apply to the entire MSR but rather to specific bits within the MSR.
3. The concept of I/O scope, which differs from functional scope.

# Scope: platform-dependent

The scope of certain power management MSRs varies by platform. For example:

* **MSR_ENERGY_PERF_BIAS** (0x1B0):
  - CPU scope on most platforms.
  - Core scope on Silvermont platforms (models 0x37, 0x4A, 0x5A, 0x4D).
  - Package scope on Westmere (models 0x2C, 0x2F, 0x25) and Sandy Bridge (models 0x2A, 0x2D).
* **MSR_POWER_CTL** (0x1FC):
  - Typically package scope.
  - Die scope on CLX-AP (Cascade Lake Xeon Advanced Performance).

# Scope: per-bit field

An MSR may control multiple features using different bits, each potentially having a distinct scope.

For example, MSR_MISC_FEATURE_CONTROL (0x1A4) manages several features with varying scopes on Atom
core-based Intel platforms.
- **DCU IP prefetcher** (bit 3): Core scope.
- **L2 hardware prefetcher** (bit 0): Module scope.

# I/O Scope

This is one of the most perplexing aspects of MSR scope and the primary reason for this article. I
spent significant amount of time understanding unexpected platform behavior while developing pepc
and experimenting with features of MSR_PKG_CST_CONFIG_CONTROL (0xE2) on Intel Xeon platforms.

* **Disclaimer 1**: The term "I/O scope" is not an industry-standard term. I coined it when I first
  encountered this concept and had to implement corresponding support in pepc.
* **Disclaimer 2**: I observed a distinct I/O scope, differing from functional scope, only with
  MSR_PKG_CST_CONFIG_CONTROL (0xE2) on certain Xeon platforms. I did not test this MSR on all Intel
  platforms, nor did I verify all MSRs. Among the MSRs I worked with, only MSR_PKG_CST_CONFIG_CONTROL
  exhibited an I/O scope distinct from its functional scope.

## Example Platform

Before discussing the concept of I/O scope, let's define a hypothetical platform for use in the
examples below.

The example platform consists of 2 packages, each containing 2 cores, with 2 CPUs per core:

* **Package 0**
  - **Core 0**
    - CPU 0
    - CPU 1
  - **Core 1**
    - CPU 2
    - CPU 3
* **Package 1**
  - **Core 2**
    - CPU 4
    - CPU 5
  - **Core 3**
    - CPU 6
    - CPU 7

Our example platform supports **MSR_BLAH**, which controls feature X with values 0 or 1:
* **Bit 0 = 1**: Feature X is enabled.
* **Bit 0 = 0**: Feature X is disabled.

## Introduction

Let's assume MSR_BLAH's feature X has package scope. Consider the following scenarios:

* Initially, feature X is disabled on all packages, so every CPU reads MSR_BLAH as "0".
* CPU 1 enables feature X by writing "1" to MSR_BLAH.

**Quiz 1**:
1. Will feature X be enabled or disabled for package 0?
2. Will feature X be enabled or disabled for package 1?

**Expected Answers**:
* Feature X will be enabled for package 0
* Feature X will be disabled for package 1.

**Quiz 2**:
1. What will CPU 0 read from MSR_BLAH?
2. What will CPU 1 read from MSR_BLAH?
3. What will CPU 2 read from MSR_BLAH?
4. What will CPU 4 read from MSR_BLAH?

**Expected Answers**:
* CPU 0 will read 1.
* CPU 1 will read 1.
* CPU 2 will read 1.
* CPU 4 will read 0.

For most MSRs, these answers are correct. However, MSR_PKG_CST_CONFIG_CONTROL (0xE2) behaves
differently due to I/O scope.

If MSR_BLAH had package scope but core I/O scope, the behavior would change, and the Quiz 2 answers
would become:
* CPU 0 would read 1.
* CPU 1 would read 1.
* CPU 2 would read 0.
* CPU 4 would read 0.

In this scenario, feature X would be enabled for package 0, but CPU 2 would still read MSR_BLAH as
"0" due to core I/O scope.

## Mental model

Let's assume MSR_BLAH has package functional scope and core I/O scope. The following mental model
helps understanding how MSR_BLAH operates.

**Disclaimer**: This mental model is my own creation and may not accurately represent the actual
hardware implementation.

Imagine is variable 'var0' inside package 0 and variable 'var1' inside package 1. MSR_BLAH is an
interface for the CPU to writes to these variables:
* Writing '0' to 'var0' disables feature X on package 0.
* Writing '1' to 'var0' enables feature X on package 0.
* Writing '0' to 'var1' disables feature X on package 1.
* Writing '1' to 'var1' enables feature X on package 1.

Imagine there are per-core "cache" variables for 'var0' and 'var1'. In our abstract platform, this would mean:
* Core 0 has a cache variable 'c0'.
* Core 1 has a cache variable 'c1'.
* Core 2 has a cache variable 'c2'.
* Core 3 has a cache variable 'c3'.

RDMSR MSR_BLAH:
* On CPUs 0 and 1: read from 'c0'.
* On CPUs 2 and 3: read from 'c1'.
* On CPUs 4 and 5: read from 'c2'.
* On CPUs 6 and 7: read from 'c3'.

WRMSR MSR_BLAH:
* On CPUs 0 and 1: write to 'c0' and 'var0'.
* On CPUs 2 and 3: write to 'c1' and 'var0'.
* On CPUs 4 and 5: write to 'c2' and 'var1'.
* On CPUs 6 and 7: write to 'c3' and 'var1'.

**Quiz**:

* Initial state:
  - Feature X is disabled on all packages, so every CPU reads MSR_BLAH as '0'.
* Modification:
  - CPU 1 enables feature X by writing '1' to MSR_BLAH.
* Questions:
  - What will CPU 0 read from MSR_BLAH?
  - What will CPU 2 read from MSR_BLAH?
  - What will CPU 4 read from MSR_BLAH?

**Answer**:
* Initially, 'var0', 'var1', 'c0', 'c1', 'c2', and 'c3' all have a value of '0'.
* CPU 1 writes '1' to 'c0' and 'var0'.
* CPU 0 reads 'c0', so it will see a value of '1'.
* CPU 2 reads 'c1', so it will see a value of '0'.
* CPU 4 reads 'c2', so it will see a value of '0'.

# MSR_PKG_CST_CONFIG_CONTROL

MSR_PKG_CST_CONFIG_CONTROL (0xE2) manages two power management features that I often use in
Intel Xeon platforms:
* **pkg_cstate_limit** (bits 2-0): Limits the deepest package C-state.
* **c1_demotion** (bit 26): Enables or disables the C1 demotion feature.

The scope of these features varies by platform. On Icelake Xeon (ICX), Sapphire Rapids
Xeon (SPR), and Emerald Rapids Xeon (EMR):
* **pkg_cstate_limit**: Package scope, core I/O scope.
* **c1_demotion**: Package scope, core I/O scope.

On Granite Rapids Xeon (GNR):
* **pkg_cstate_limit**: Package scope, core I/O scope.
* **c1_demotion**: Core scope, core I/O scope.

On Sierra Fores Xeon and Grand Ridge SoC:
* **pkg_cstate_limit**: Package scope, core I/O scope.
* **c1_demotion**: Package scope, module I/O scope.

# Example

Let's explore MSR_PKG_CST_CONFIG_CONTROL on Intel Icelake Xeon using the 'rdmsr' and 'wrmsr' Linux
tools. These tools allow direct reading and writing of MSRs but require careful handling to avoid
misconfiguration. The [pepc](https://github.com/intel/pepc) tool simplifies this process by
providing a user-friendly interface, reducing errors, and helping to identify platform-specific
nuances. It is particularly useful for understanding complex scenarios, such as those involving I/O
scope differences.

## Initial configuration

Set the package C-state limit to PC0 (0) and disable C1 demotion for all CPUs as follows:

```
pepc cstates config --c1-demotion off --pkg-cstate-limit pc0 --cpus all
```

Here is how this could be done with wrmsr:

```
# Read current value on whatever CPU.
$ rdmsr 0xE2
14000402

# Current values are: pkg_cstate_limit = PC6 = 3 in bits 2-0
#                     c1_demotion enabled, bit 26.
# New value: pkg_cstate_limit = PC0 = 0 in bits 2-0
#            c1_demotion disabled, bit 26.
$ wrmsr --all 0xE2 0x10000400
```

Note: On certain Icelake Xeon systems, the package C-state limit may be locked, preventing OS-level
modifications. On my system, this lock can be disabled via a BIOS option.

## Topology

The Ice Lake Xeon system used had the following topology:
* Two packages.
* 36 cores per package.
* Two CPUs per core.

Topology details can be checked with 'pepc topology info'. Here are relevant numbers for the examples:
* CPUs 0-35 and 72-107 belong to package 0.
* CPUs 36-71 and 108-143 belong to package 1.
* CPUs 0 and 72 belong to core 0 of package 0.
* CPUs 1 and 73 belong to core 1 of package 0.
* CPUs 36 and 108 belong to core 0 of package 1.
* CPUs 37 and 109 belong to core 1 of package 1.

## Confusing configuration

Enable C1 demotion and set the package C-state limit to PC6 by writing to the MSR from CPU 0:

```
# Write the new value to MSR_PKG_CST_CONFIG_CONTROL on CPU 0.
$ wrmsr --processor 0 0xE2 0x14000402

# Verify the value on CPUs 0 and 72, as both share the same core I/O scope.
$ rdmsr --processor 0 0xE2
14000402
$ rdmsr --processor 72 0xE2
14000402

# Check the value on CPU 1, which is in a different core. It should remain unchanged.
$ rdmsr --processor 1 0xE2
10000400
```

Since the last write to the MSR set 'pkg_cstate_limit=2' (PC6) for CPU 71, we know this is the value
used by the processor for package 0. Although reading the MSR from CPU 1 shows the limit as PC0, the
actual limit for the package is PC6. This behavior can be confusing, as the effective package C-state
limit is determined by the most recent write.

The [pepc](https://github.com/intel/pepc) tool accounts for I/O scope and provides a helpful warning
in such cases. This feature has previously saved some users significant troubleshooting time.

```
$ pepc cstates info --pkg-cstate-limit
pepc: warning: cannot determine package C-state limit for package 0:
  CPU 0 has value 'PC6', but CPU 1 has value 'PC0', even though they are in the same package.
  This situation is possible because package C-state limit has 'package' scope, but 'core' I/O scope.
Package C-state limit: 'PC6' for CPUs 0,72
Package C-state limit: 'PC0' for CPUs 1-71,73-143
```

## Enable PC6

To verify the actual package C-state limit used by the processor, ensure the limit is set to PC6 for
both packages. On Ice Lake Xeon, packages transition to and from PC6 together, so both must be
configured consistently.

```
# CPU 36 is in package 1. Set the limit to PC6.
$ wrmsr --processor 36 0xE2 0x14000402

# Verify the value on CPUs 36 and 108, as they share the same core I/O scope.
$ rdmsr --processor 36 0xE2
14000402
$ rdmsr --processor 108 0xE2
14000402

# Check CPU 37, which is in a different core of package 1. The value should remain
# unchanged.
$ rdmsr --processor 37 0xE2
10000400
```

## Verify PC6

Use turbostat to verify PC6 residency and confirm that the platform enters PC6.

```
$ turbostat -q -S --num_iterations 1 --interval 1 --show Pkg%pc6
Pkg%pc6
78.43
```

This indicates the platform was in PC6 for 78.43% of the 1-second measurement interval.

## More confusing configuration

Now let's involve CPU1, and set set the package C-state limit to PC0 by writing
pkg_cstate_limit=0 to MSR_PKG_CST_CONFIG_CONTROL on CPU 1.

```
# What limit CPU 1 reports?
$ rdmsr --processor 1 0xE2
10000400

# OK, PC0. But we know the actual limit is PC6. Double-check this with turbostat.
$ turbostat -q -S --num_iterations 1 --interval 1 --show Pkg%pc6
Pkg%pc6
69.32

# The actual limit is indeed, PC6. Now set it to PC0 via CPU 1.
$ wrmsr --processor 1 0xE2 0x10000400

# Let's see what turbostat reports.
$ turbostat -q -S --num_iterations 1 --interval 1 --show Pkg%pc6
Pkg%pc6
0.00

# No PC6 residency. The new actual limit is PC0.
```

This configuration is confusing due to core I/O scope.

## Clarify the situation

Here's how pepc helps clarify the situation:

```
$ pepc cstates info --pkg-cstate-limit
pepc: warning: cannot determine package C-state limit for package 0:
  CPU 0 has value 'PC6', but CPU 1 has value 'PC0', even though they are in the same package.
  This situation is possible because package C-state limit has 'package' scope, but 'core' I/O scope.
Package C-state limit: 'PC6' for CPUs 0,36,72,108
Package C-state limit: 'PC0' for CPUs 1-35,37-71,73-107,109-143
```

This warning is highly beneficial and has saved several users significant troubleshooting time.
