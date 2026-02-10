<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Intel CPU Base Frequency Explained: Definitions and Performance Scaling Fundamentals

- Author: Artem Bityutskiy \<dedekind1@gmail.com\>
- Date: January, 2026

## Introduction

A couple of decades ago, the term "base frequency" was standard and unambiguous in the context of
Intel CPUs. It simply meant the maximum frequency all processors could sustain indefinitely under
normal cooling conditions.

Today, however, the situation has become more complex:

- Intel no longer uses this term consistently in CPU specifications and marketing materials
- The base frequency referenced in the Intel SDM differs from what the Linux kernel reports in the
  `base_frequency` sysfs file
- The term is easily confused with other related terms such as "guaranteed performance"
- In general, the notion of base frequency has become less relevant for modern Intel CPUs and not
  very useful for software

This document was initially created to clarify and unpack the two meanings of "base frequency":
the Intel SDM meaning and the Linux kernel meaning. The goal was to just document the differences
and explain the reasons behind them, helping Linux power management developers navigate the
complexity and historical baggage behind the term.

However, properly explaining "base frequency" requires understanding the broader context of Intel
CPU performance scaling in Linux. As a result, the document has expanded in scope to cover many
general concepts related to this topic. Readers already familiar with ACPI CPPC, the Linux
`intel_pstate` driver, and Intel CPU performance scaling interfaces may skip directly to the
[Base Frequency: Relevance](#base-frequency-relevance) and
[Base Frequency: Definitions](#base-frequency-definitions) sections. Alternatively, you can read the
"Key Takeaways" subsections in the preceding sections for a high-level summary, and then skip to the
base frequency sections.

This is not a comprehensive guide, but rather an introduction to Intel CPU performance scaling in
Linux, focusing on terminology and key concepts, with particular attention to disambiguating "base
frequency".

## Table of Contents

- [Introduction](#introduction)
- [Disclaimer](#disclaimer)
- [Overview](#overview)
- [ACPI](#acpi)
  - [P-States](#p-states)
  - [Legacy ACPI P-States](#legacy-acpi-p-states)
  - [ACPI CPPC](#acpi-cppc)
  - [Key CPPC Performance Levels](#key-cppc-performance-levels)
    - [Nominal Performance](#nominal-performance)
    - [Guaranteed Performance](#guaranteed-performance)
    - [Highest Performance](#highest-performance)
    - [Lowest Performance](#lowest-performance)
  - [Key Takeaways](#key-takeaways)
- [Linux Kernel](#linux-kernel)
  - [Linux CPU Frequency sysfs ABI](#linux-cpu-frequency-sysfs-abi)
  - [CPU Frequency Translation](#cpu-frequency-translation)
  - [ACPI CPPC sysfs ABI](#acpi-cppc-sysfs-abi)
  - [The intel_pstate Driver](#the-intel_pstate-driver)
  - [Key Takeaways](#key-takeaways-1)
- [Intel CPU Performance Scaling](#intel-cpu-performance-scaling)
  - [Intel SpeedStep](#intel-speedstep)
  - [Intel HWP](#intel-hwp)
  - [Performance Level to Frequency Mapping](#performance-level-to-frequency-mapping)
  - [Key HWP Performance Levels](#key-hwp-performance-levels)
    - [HWP vs ACPI CPPC Mapping](#hwp-vs-acpi-cppc-mapping)
  - [Key Takeaways](#key-takeaways-2)
- [Base Frequency: Relevance](#base-frequency-relevance)
  - [Traditional Meaning](#traditional-meaning)
  - [Modern Client CPUs](#modern-client-cpus)
  - [Base Frequency in Marketing Materials](#base-frequency-in-marketing-materials)
  - [Frequency vs Performance](#frequency-vs-performance)
  - [Key Takeaways](#key-takeaways-3)
- [Base Frequency: Definitions](#base-frequency-definitions)
  - [Fixed Base Frequency (Intel SDM)](#fixed-base-frequency-intel-sdm)
  - [Sysfs Base Frequency (Linux Kernel Definition)](#sysfs-base-frequency-linux-kernel-definition)
  - [Sysfs vs Fixed Base Frequency](#sysfs-vs-fixed-base-frequency)
  - [Key Takeaways](#key-takeaways-4)
- [Conclusions](#conclusions)
- [Appendix: CPPC vs HWP Performance Levels](#appendix-cppc-vs-hwp-performance-levels)
  - [Alder Lake](#alder-lake)
  - [Raptor Lake](#raptor-lake)
  - [Meteor Lake](#meteor-lake)
  - [Arrow Lake](#arrow-lake)
  - [Lunar Lake](#lunar-lake)
  - [Panther Lake](#panther-lake)

## Disclaimer

While this document aims to provide accurate information, it is not an official specification and
is based on the author's experience and understanding. For authoritative information, please refer
to the Linux kernel documentation and source code, the ACPI specification, and official Intel
documentation.

And make sure to keep the date of the document in mind. The knowledge cutoff is the end of 2025.

## Overview

This document begins with background sections covering concepts necessary to understand base
frequency:

- **ACPI**: P-states and key ACPI CPPC performance levels
- **Linux Kernel**: CPU frequency sysfs ABI and the `intel_pstate` driver
- **Intel CPU**: SpeedStep and HWP interfaces, performance level to frequency mapping, and HWP vs
  CPPC performance levels

Following these foundational topics, the [Base Frequency: Relevance](#base-frequency-relevance)
and [Base Frequency: Definitions](#base-frequency-definitions) sections provide detailed coverage
of the term and its various meanings.

## ACPI

This section introduces key ACPI (Advanced Configuration and Power Interface) terms and concepts
relevant to CPU performance scaling.

### P-States

**P-states** (performance states) are an abstraction introduced by ACPI to represent different
levels of CPU performance and power consumption. P-states are numbered P0, P1, P2, and so on, where
P0 represents the highest performance and maximum power consumption. They are defined by the
platform hardware or firmware and allow the OS to manage CPU power and performance by requesting
specific P-states.

In practice, P-states are primarily implemented through CPU frequency and voltage scaling. Higher
performance means higher CPU frequency and voltage, which results in higher power consumption. On Intel
CPUs, P-states may also involve other parameters such as CPU interconnect or shared cache frequency.

On Intel CPUs, P1 typically represents the CPU base frequency, while P0 represents the maximum turbo
frequency.

### Legacy ACPI P-States

Before ACPI version 5.0, CPU performance management was based on P-states defined by the `_PSS`
(Performance Supported States) ACPI object. In this legacy approach, P-states directly correspond
to specific CPU frequency values in MHz, and the OS simply requests the desired CPU frequency via
the register defined by the `_PCT` (Performance Control) ACPI object.

While modern Intel platforms support legacy ACPI P-states for backward compatibility, modern Linux
kernels on modern Intel CPUs use the ACPI CPPC mechanism instead.

### ACPI CPPC

ACPI specification version 5.0 introduced the Collaborative Processor Performance Control (CPPC)
feature, which defines P-states using abstract, unitless integer CPU performance levels rather
than explicit CPU frequency values.

To enumerate CPPC performance levels, the OS calls the `_CPC` (Continuous Performance Control) ACPI
method, which returns key performance level values such as lowest, nominal, and highest performance
levels. The OS can then request any performance level within the [lowest, highest] range.

CPPC also introduces **Autonomous Selection Mode**, where the OS only sets the minimum and maximum
performance levels, and the CPU autonomously selects the actual performance level based on workload
and other factors (e.g., thermal conditions). This corresponds to the "Hardware P-states" (HWP)
feature on modern Intel platforms.

### Key CPPC Performance Levels

ACPI CPPC introduces terminology for several key performance levels.

#### Nominal Performance

Chapter 8 of the [ACPI specification v6.6](https://uefi.org/specs/ACPI/6.6/) defines nominal performance
as follows:

> Nominal Performance is the maximum sustained performance level of the processor, assuming ideal
> operating conditions. In absence of an external constraint (power, thermal, etc.) this is the
> performance level the platform is expected to be able to maintain continuously. All processors are
> expected to be able to sustain their nominal performance state simultaneously.

The key characteristic is the **system-wide guarantee**: all CPUs can run at nominal performance
simultaneously, while higher performance levels may only be achievable on a subset of CPUs for
limited durations.

Some Intel platforms also provide **nominal frequency**, an optional CPPC field that specifies the
CPU frequency corresponding to the nominal performance level. The `intel_pstate` Linux kernel driver
uses this value to calculate the performance-level-to-frequency scaling factor on some platforms
(discussed in more detail in the [Performance Level to Frequency Mapping](#performance-level-to-frequency-mapping)
section).

#### Guaranteed Performance

Guaranteed performance is the maximum sustainable performance level under current conditions.
It differs from nominal performance as follows:

| Nominal Performance      | Guaranteed Performance        |
|--------------------------|-------------------------------|
| Mandatory                | Optional                      |
| Assumes ideal conditions | Reflects current conditions   |
| Static, never changes    | Dynamic, can change real-time |

ACPI CPPC requires guaranteed performance to be less than or equal to nominal performance.

#### Highest Performance

ACPI CPPC defines highest performance as follows:

> Highest performance is the absolute maximum performance an individual processor may reach, assuming
> ideal conditions. This performance level may not be sustainable for long durations, and may only be
> achievable if other platform components are in a specific state. For example, it may require other
> processors be in an idle state.

This represents the absolute peak performance a CPU can reach, potentially only for short durations
and under specific conditions.

#### Lowest Performance

ACPI CPPC defines two lowest performance levels:

- **Lowest Performance**: The absolute lowest performance level of the platform.
- **Lowest Nonlinear Performance**: The lowest performance level at which nonlinear power savings
  are achieved (per the ACPI specification).

The key distinction is that lowest nonlinear performance represents the lower boundary for normal
CPU power management algorithms. Operating below this level yields diminishing power savings and
should typically be reserved for emergency situations (e.g., thermal throttling).

### Key Takeaways

Legacy vs. Modern ACPI CPU Performance Scaling Interfaces:

- **Legacy P-states** are directly bound to CPU frequencies in MHz.
- **CPPC** uses unitless performance levels instead of frequencies.
- Modern Linux on modern Intel platforms uses CPPC by default.

Key CPPC Performance Levels:

- **Lowest Performance**: Absolute minimum performance level.
- **Lowest Nonlinear Performance**: Energy-efficient minimum (boundary for normal operation).
- **Guaranteed Performance**: Optional, maximum sustainable in current conditions.
- **Nominal Performance**: Maximum sustainable under ideal conditions (system-wide guarantee).
- **Highest Performance**: Absolute peak performance.

**Note:** CPPC always provides lowest and highest performance levels as integers, and the OS can
request any integer value within this range.

## Linux Kernel

This section discusses various Linux kernel aspects related to CPU frequency scaling on Intel
platforms.

### Linux CPU Frequency sysfs ABI

The Linux kernel's CPU performance scaling user-space interface is implemented via sysfs and uses
CPU frequency values in kHz.

The sysfs interface exposes frequency control through files in
`/sys/devices/system/cpu/cpuN/cpufreq/`, where `N` is the CPU number. Here are some key files:

```bash
$ ls -1 /sys/devices/system/cpu/cpu0/cpufreq/ | grep -E 'min|max|cur'
scaling_cur_freq # Current frequency in kHz
scaling_max_freq # OS-requested maximum frequency in kHz
scaling_min_freq # OS-requested minimum frequency in kHz
cpuinfo_max_freq # Maximum frequency supported by hardware in kHz
cpuinfo_min_freq # Minimum frequency supported by hardware in kHz
```

Refer to the
[Linux kernel documentation](https://docs.kernel.org/admin-guide/pm/cpufreq.html)
for more information about the cpufreq sysfs interface.

### CPU Frequency Translation

Both ACPI CPPC and Intel CPUs use performance levels for CPU performance scaling rather than CPU
frequency values. However, the Linux kernel ABI exposes CPU frequency values in kHz to user space.
This creates a translation challenge that the `intel_pstate` kernel driver addresses by internally
converting between performance levels and CPU frequency values.

Since Linux tools such as `turbostat` can measure actual CPU frequency using the APERF/MPERF
ratio (see [this article](https://github.com/intel/pepc/blob/main/docs/misc-tsc-amperf.md) for
details), the kernel must perform this translation with reasonable precision. Otherwise, users may
observe inconsistencies between requested and measured frequencies.

### ACPI CPPC sysfs ABI

Modern Intel platforms support ACPI CPPC, and the Linux kernel exposes CPPC performance levels via
`/sys/devices/system/cpu/cpuN/acpi_cppc/`, where `N` is the CPU number. Here is an example from a
Raptor Lake system
([Intel i5-1340P](https://www.intel.com/content/www/us/en/products/sku/232126/intel-core-i51340p-processor-12m-cache-up-to-4-60-ghz/specifications.html)):

```bash
$ cd /sys/devices/system/cpu/cpu0/acpi_cppc/
$ grep '' -- *_perf
guaranteed_perf:25        # Guaranteed performance level
highest_perf:59           # Highest performance level
lowest_nonlinear_perf:18  # Lowest nonlinear performance level
lowest_perf:1             # Lowest performance level
nominal_perf:24           # Nominal performance level
reference_perf:27         # Reference performance level
```

Note that ACPI tables are implemented in BIOS, which is typically developed by the platform vendor,
not by Intel Corporation. Consequently, these ACPI CPPC values may reflect the platform vendor's
interpretation of the ACPI specification and take into account the actual thermal design of the
product.

### The intel_pstate Driver

The `intel_pstate` kernel driver is the default CPU frequency scaling driver for Intel platforms.
It supports both server and client CPUs, and implements all required functionality for CPU
performance scaling in Linux. For example, it handles the translation between performance levels
and CPU frequency values for CPU models that require it. When necessary, it also implements
workarounds and platform-specific quirks.

If `intel_pstate` is disabled (e.g., via the `intel_pstate=disable` kernel command line option),
the Linux kernel falls back to the generic `acpi_cpufreq` driver, which uses legacy ACPI P-states.
However, this is not a recommended configuration for modern Intel platforms.

The `intel_pstate` driver reads ACPI data when necessary but directly programs CPU performance
scaling registers rather than invoking ACPI methods. In other words, the driver
**largely bypasses** ACPI CPU performance management data and methods.

### Key Takeaways

- Linux provides a frequency-based CPU performance scaling API via sysfs, while modern Intel CPUs use
  abstract performance levels.
- The `intel_pstate` driver is the default CPU frequency scaling driver for modern Intel platforms:
  - Translates between performance levels and frequencies when needed.
  - Directly programs CPU registers, largely bypassing ACPI methods.
- ACPI CPPC performance levels are separately available via sysfs.

## Intel CPU Performance Scaling

This section discusses Intel CPU power management features relevant to CPU performance scaling in
Linux:

- Intel CPU performance scaling interfaces
- Performance levels and their mapping to CPU frequency
- Key HWP performance levels

### Intel SpeedStep

The Intel SpeedStep interface was introduced with Pentium M processors, making it available since
around 2004.

- **Enumeration**: CPUID.1.ECX[7] (CPUID instruction, leaf 1, bit 7 of the ECX register). The bit is
  called "EIST", which stands for Enhanced Intel SpeedStep Technology.
- **Enable/Disable**: The feature can be enabled/disabled via IA32_MISC_ENABLE[16] (MSR 0x1A0, bit
  16).

Intel SpeedStep allows the OS to request specific P-states by writing the corresponding performance
level to IA32_PERF_CTL[15:8] (MSR 0x199, bits 15:8). In response, the CPU transitions to the
requested P-state if thermal, power, and other constraints permit.

To read the current P-state, the OS reads IA32_PERF_STATUS[15:8] (MSR 0x198, bits 15:8), which
returns the current performance level.

How performance levels map to CPU frequency is discussed in the
[Performance Level to Frequency Mapping](#performance-level-to-frequency-mapping) subsection.

### Intel HWP

Intel HWP (Hardware P-states) is a modern CPU performance scaling interface introduced with Skylake
processors in 2015.

The main idea behind HWP is to offload CPU performance management from the OS to the CPU itself. With
HWP, the OS does not need to continuously track workload changes and adjust CPU performance on demand.
Instead, the OS only sets the minimum and maximum performance levels, and the CPU autonomously
selects the actual performance level based on workload and other factors (e.g., thermal conditions).

The key difference:

- **SpeedStep**: "Use this exact performance level."
- **HWP**: "Here are the constraints, you choose the optimal performance level."

**Enumeration and Control:**

- **Enumeration**: CPUID.06H.EAX[7] indicates HWP support.
- **Enable/Disable**: IA32_PM_ENABLE[0] (MSR 0x770) enables HWP globally.

With HWP, the OS sets minimum and maximum performance levels via IA32_HWP_REQUEST (MSR 0x774), and
the CPU autonomously selects the actual performance level within this range.

The SDM explicitly states that IA32_PERF_CTL should not be used when HWP is enabled. For reading
the current performance level, the SDM does not discuss IA32_PERF_STATUS usage with HWP. Instead,
it recommends using the APERF/MPERF ratio to measure actual CPU performance.

Intel HWP implements ACPI CPPC's Autonomous Selection Mode, where the OS sets constraints and the
hardware autonomously manages the actual performance level.

The HWP interface is richer than SpeedStep, providing additional MSRs for capabilities reporting,
interrupt control, and advanced features such as Energy Performance Preference (EPP) hints and
activity window specifications. For detailed information, refer to the Intel Software Developer's
Manual (SDM) Volume 3B, Chapter 14.

Note that HWP MSRs are architectural, indicated by the "IA32_" prefix in their names. This means
that all Intel CPUs supporting HWP implement these MSRs with the same semantics.

### Performance Level to Frequency Mapping

Both Intel SpeedStep and HWP interfaces use abstract performance levels for CPU performance scaling.
The SDM does not explicitly define what performance levels mean or how they map to CPU frequency,
though it mentions that the mapping is platform-specific.

In practice, on all Intel platforms except hybrid CPUs, CPU frequency equals the performance
level multiplied by the Base Clock frequency, which is 100 MHz on modern Intel platforms
(starting from 2015). For example, performance level 15 corresponds to a CPU frequency of
1500 MHz (15 × 100 MHz).

The situation is more complex for hybrid client CPUs. Note that all modern Intel client CPUs
(since Alder Lake in 2021) are hybrid. As of 2025, Intel's hybrid client CPU families include
Alder Lake, Raptor Lake, Meteor Lake, Arrow Lake, Lunar Lake, and Panther Lake.

These hybrid CPUs integrate different core types, though not all platforms include all three types:

- **P-cores** (Performance cores): Optimized for performance and latency-sensitive workloads.
- **E-cores** (Efficient cores): Optimized for power efficiency.
- **LPE-cores** (Low Power Efficient cores): Optimized for low power (e.g., background tasks).

Intel aims to keep performance levels reflective of actual CPU performance across all core types.
However, since different core types have different characteristics (microarchitecture, cache sizes,
etc.), the same performance level may correspond to different CPU frequencies on different core
types.

Since the Linux kernel ABI is frequency-based, the kernel must map performance levels to CPU
frequencies and vice versa. Fortunately, the mapping remains linear (or nearly linear) on modern
Intel hybrid client CPUs, though the scaling factors differ between core types.

For example, on **Meteor Lake**:

- **P-cores**: Performance level × 80000 = Frequency (in kHz)
- **E-cores**: Performance level × 100000 = Frequency (in kHz)
- **LPE-cores**: Performance level × 100000 = Frequency (in kHz)

The mapping is implemented in the `intel_pstate` driver. For some platforms, such as Alder Lake and
Meteor Lake, the driver hardcodes the scaling factors. For others, such as Lunar Lake, the driver
calculates the scaling factors based on ACPI CPPC nominal performance level and nominal frequency:

Scaling Factor = Nominal Frequency / Nominal Performance Level

This scaling factor enables bidirectional conversion:

- CPU Frequency = Performance Level × Scaling Factor
- Performance Level = CPU Frequency / Scaling Factor

Note that this approach relies on ACPI CPPC using the same performance level numbering scheme as
Intel CPUs.

So far, the linear mapping has allowed the `intel_pstate` driver to support Linux's frequency-based
API with minimal complexity. However, whether this linear mapping will hold for future Intel hybrid
client CPUs is uncertain.

### Key HWP Performance Levels

The Intel SDM introduces several key performance levels in the context of HWP, which are used by the
`intel_pstate` driver. Unfortunately, the terminology partially differs from ACPI CPPC.

These performance levels are available via IA32_HWP_CAPABILITIES (MSR 0x771). Here are the key
levels and what SDM says about them:

- **Highest Performance**: The peak performance level.
  - May not always be reachable depending on thermal and power conditions, workload, and other
    factors.
  - Corresponds to the maximum single-core turbo frequency.
- **Guaranteed Performance**: Hardware's best-effort approximation of sustainable performance.
  - Dynamic, can change during operation. Examples of scenarios that may change it:
    - System hits RAPL package power limit, for example when a laptop switches between AC
      and battery power sources.
    - CPU temperature approaches critical thermal limits, for example activating the TCC (Thermal
      Control Circuit).
    - User changes the TDP level using the Intel SST-PP (Speed Select Technology - Performance
      Profile) interface.
    - External agent, such as a BMC (Baseboard Management Controller), modifies platform power
      settings.
- **Most Efficient Performance**: Most energy-efficient performance level.
  - Sweet spot for performance-per-watt.
  - Practical lower limit for operation.
- **Lowest Performance**: Minimum performance level the OS can request.
  - Absolute floor for IA32_HWP_REQUEST.

#### HWP vs ACPI CPPC Mapping

While Intel HWP and ACPI CPPC use different terminology, there is a conceptual mapping between their
performance levels. Based on the performance level definitions and empirical data from existing
hybrid Intel client platforms
(see [Appendix: CPPC vs HWP Performance Levels](#appendix-cppc-vs-hwp-performance-levels) for details),
the following mapping can be derived:

| Intel HWP Performance Level | ACPI CPPC Performance Level                               | Match Quality                                                         |
|-----------------------------|-----------------------------------------------------------|-----------------------------------------------------------------------|
| Highest Performance         | Highest Performance                                       | Perfect: always identical across all platforms and core types         |
| Guaranteed Performance      | Guaranteed Performance, or if absent, Nominal Performance | Strong: exact match when Guaranteed present, close match with Nominal |
| Most Efficient Performance  | Lowest Nonlinear Performance                              | Variable: perfect on some platforms, differences on others            |
| Lowest Performance          | Lowest Performance                                        | Perfect: always identical across all platforms and core types         |

### Key Takeaways

1. Two interfaces:
   - **SpeedStep** (legacy): OS explicitly requests specific P-states.
   - **HWP** (modern): OS sets constraints, CPU manages performance autonomously.
   - Both interfaces use performance levels, not frequency values directly.

2. Performance level to frequency mapping:
   - **Non-hybrid CPUs**: Performance Level × 100 MHz = CPU Frequency
   - **Hybrid CPUs**: Different scaling factors per core type

3. **The `intel_pstate` driver** handles performance-level-to-frequency translation to implement
   Linux's frequency-based ABI.
   - The mapping has been linear so far, but future hybrid architectures may use more complex
     mappings.

4. Key HWP performance levels (via IA32_HWP_CAPABILITIES):
   - **Highest Performance**: Absolute peak, may not be sustainable.
   - **Guaranteed Performance**: Dynamic, sustainable under current conditions.
   - **Most Efficient Performance**: Sweet spot for performance-per-watt.
   - **Lowest Performance**: Absolute minimum.

## Base Frequency: Relevance

This section discusses how base frequency has become less relevant and useful for modern Intel CPUs.
Specific definitions are provided in the [Base Frequency: Definitions](#base-frequency-definitions)
section.

### Traditional Meaning

The traditional meaning of the base frequency is that it is the guaranteed frequency that all cores
can sustain indefinitely, assuming the cooling solution is adequate.

What is an adequate cooling solution? Intel processors have a TDP (Thermal Design Power) rating,
which indicates the maximum power in Watts that the cooling solution must be able to dissipate. If
the cooling solution can dissipate at least TDP Watts, the CPU can run at base frequency
indefinitely.

This traditional meaning usually still holds for Intel Xeon server processors, which are
typically used in designs with robust cooling solutions. However, there are caveats even for server
processors. For example, AVX-512 vector instructions may cause the CPU to reduce its frequency
below base frequency to stay within power limits.

Therefore, when using the term "base frequency", it should be viewed as a "best estimate" of
sustainable frequency for all cores under normal conditions and certain workload types, rather than
as a strict guarantee.

Frequency above base frequency is achievable only for a limited time, when there is sufficient
thermal and power headroom. In general, the better the cooling solution, the longer the CPU can
sustain frequencies above base frequency.

Intel marketing material typically advertises the base frequency, maximum turbo frequency, and
all-core turbo frequency for server processors. For example, the
[Intel Xeon 6788P](https://www.intel.com/content/www/us/en/products/sku/241837/intel-xeon-6788p-processor-336m-cache-2-00-ghz/specifications.html)
specifications list:

- Base Frequency: 2.0 GHz
- Max Turbo Frequency: 3.8 GHz
- All-Core Turbo Frequency: 3.2 GHz

Max turbo frequency (also called single-core turbo) is the maximum frequency achievable on a single
core when other cores are idle. All-core turbo frequency is the maximum turbo frequency achievable
when all cores are active.

### Modern Client CPUs

Old Intel client CPUs (e.g., Sandy Bridge from 2011) followed the traditional meaning of base
frequency: the guaranteed frequency that all cores can sustain indefinitely, assuming adequate
cooling.

Over time, Intel client CPUs evolved such that the traditional concept of base frequency became
harder to apply. Here are some reasons:

1. **Variable cooling**: Ultrabooks and mobile devices have limited cooling that varies with power
   mode (plugged vs. battery, silent vs. performance). This makes "indefinitely sustainable"
   frequency context-dependent.
2. **Integrated components**: Graphics, AI accelerators, and media engines share the power and thermal
   budget, making it hard to define a CPU base frequency independent of other components.
3. **Heterogeneous cores**: All modern Intel clients are hybrid and include different core types
   (P-cores, E-cores, LPE-cores), which have different performance characteristics, making it hard
   to define a single base frequency value.

For modern Intel client CPUs, especially mobile ones, base frequency is no longer a useful
concept.

### Base Frequency in Marketing Materials

While Intel still advertises base frequency for server and some desktop client CPUs (e.g., hybrid
CPUs with only P-cores included), it stopped doing so for mobile client CPUs starting with
Alder Lake (12th Gen, 2021). For example,
[Intel Core i5-12450H](https://www.intel.com/content/www/us/en/products/sku/132222/intel-core-i512450h-processor-12m-cache-up-to-4-40-ghz/specifications.html)
specifications list only maximum turbo frequencies: 4.4 GHz (P-core) and 3.3 GHz (E-core).

The CPU branding string from CPUID used to include base frequency (e.g., "Intel(R) Core(TM)
i7-7500U CPU @ 2.70GHz" for Kaby Lake) but no longer does (e.g., "Intel(R) Core(TM) Ultra 7 256V"
for Lunar Lake). Server CPUs have also removed base frequency from branding strings.

### Frequency vs Performance

Another trend is that the notion of CPU frequency as a measure of performance continues to weaken.
Increasing CPU frequency does not always translate to proportional performance gains.

Real-world performance depends on many factors: workload nature (compute vs. I/O-bound), power
and thermal constraints, integrated accelerators, and more. This makes frequency less relevant as
a performance metric.

The Intel CPU HWP interface, as well as modern ACPI CPPC, also use abstract performance levels
rather than frequency values, further decoupling performance from frequency.

This trend adds to the reasons why base frequency is becoming less useful for modern Intel CPUs.

### Key Takeaways

1. **Traditional meaning**: Base frequency is the guaranteed frequency all cores can sustain
   indefinitely with adequate cooling. Still generally applicable to server processors.
2. **Modern client CPUs**: Base frequency is difficult to define due to variable cooling, integrated
   components sharing power/thermal budget, and heterogeneous cores with different characteristics.
3. **Marketing evolution**: Intel has phased out base frequency from mobile client CPU specifications
   (since Alder Lake 2021) and CPU branding strings, though it remains for server and some desktop CPUs.
4. **Declining relevance**: Base frequency is becoming less meaningful as a performance metric.

## Base Frequency: Definitions

For modern Intel client CPUs, it is best to avoid using the "base frequency" term altogether.
However, if the term must be used, be sure to clarify which definition is meant. There are two
"base frequencies":

- CPUID.16H.EBX[15:0] or MSR_PLATFORM_INFO base frequency (Intel SDM, referred to as
  fixed base frequency in this document)
- `/sys/devices/system/cpu/cpuN/cpufreq/base_frequency` (Linux kernel definition, referred to as
  sysfs base frequency in this document)

They mean the same thing for non-hybrid Intel CPUs (servers and older clients), but differ for modern
hybrid Intel client CPUs.

### Fixed Base Frequency (Intel SDM)

Intel SDM specifies two ways to get base frequency:

- **CPUID.16H**: Returns processor base frequency in MHz
- **MSR 0xCE (MSR_PLATFORM_INFO)** bits 15:8: Maximum Non-Turbo Ratio

However, the SDM does not define the meaning of base frequency and says nothing about its
sustainability.

Let's take a look at a practical example on a modern hybrid client CPU:
[Intel Core i5-1340P](https://www.intel.com/content/www/us/en/products/sku/232126/intel-core-i51340p-processor-12m-cache-up-to-4-60-ghz/specifications.html)
(Raptor Lake), CPUs 0-7 are P-cores and CPUs 8-15 are E-cores.

CPUID.16H reports 2.2 GHz base frequency for both core types:

```bash
$ cpuid -l 0x16
CPU 0:
   Processor Frequency Information (0x16):
      Core Base Frequency (MHz) = 0x898 (2200)
      Core Maximum Frequency (MHz) = 0x11f8 (4600)
      Bus (Reference) Frequency (MHz) = 0x64 (100)
... snip ...
CPU 15:
   Processor Frequency Information (0x16):
      Core Base Frequency (MHz) = 0x898 (2200)
      Core Maximum Frequency (MHz) = 0xd48 (3400)
      Bus (Reference) Frequency (MHz) = 0x64 (100)
```

MSR_PLATFORM_INFO[15:8] reports the same ratio for both core types:

```bash
$ rdmsr 0xCE --processor 0
804043df0811600
$ rdmsr 0xCE --processor 15
804043df0811600
```

The ratio value is 0x16 (22 decimal), which corresponds to 2.2 GHz (22 × 100 MHz). This base
frequency value is independent of core type. Checking other hybrid Intel CPUs shows the same
characteristic: a single base frequency value applies to all core types. Additionally, this value
is static and never changes for a given processor. Hence the term "fixed base frequency" used in
this document, though this is not an official designation.

**Practical Meaning**: The fixed base frequency corresponds to the "default" MPERF and TSC
counters rate. On the Raptor Lake CPU shown above, the MPERF counter increments at a 2.2 GHz rate,
regardless of core type or actual CPU frequency. The fixed base frequency value is also very close
to the TSC rate.

Now, the caveat here is "default rate". Some Intel CPUs support configurable TDP levels. When
the platform vendor uses the non-default TDP level, the MPERF and TSC rates may change, but the
fixed base frequency value remains the same.

Clearly, this may not always represent the guaranteed, sustainable CPU frequency, as in the
traditional meaning. It is simply the rate of an internal counter. Nothing more than that. While
this definition may not be immediately useful for most use cases, it describes what the fixed base
frequency represents in practice.

Important: This is not an official definition. This is an empirical observation based on testing
and inspecting code of the Linux kernel and the open-source Linux `turbostat` tool. It may
not hold for future Intel processors.

To learn more about TSC and MPERF, please check the following article:
[TSC, APERF, and MPERF Counters](https://github.com/intel/pepc/blob/main/docs/misc-tsc-amperf.md).

Let's verify this definition by measuring TSC and MPERF rates on the same Raptor Lake system
(which does not support configurable TDP levels).

```bash
$ rdmsr --processor 0 0x10 # Read the TSC (MSR alternative to 'RDTSC' instruction)
$ rdmsr --processor 0 0xe7 # Read MPERF

# Run a busy loop on CPU 0 for 1 hour in background. This will make sure CPU 0 does not
# enter C-states, which pause the MPERF counter.
$ taskset -c 0 sh -c 'while :; do :; done'&
# Wait for 1 hour. The longer the measurement period, the more accurate the result.
# Note: While Linux kernel timekeeping is based on TSC, this measurement is still valid because
# the system adjusts time via NTP, measuring TSC rate against NTP-corrected system time.
$ sleep 3600

# Read TSC and MPERF again.
$ rdmsr --processor 0 0x10
$ rdmsr --processor 0 0xe7
# Terminate the busy loop.
$ kill %1
88cf7ee1d14b
3634e64b38
8ffa1b97579b
765f634f828
```

Calculating the rates:

- TSC rate: (0x8ffa1b97579b - 0x88cf7ee1d14b) / 3600.0 ≈ 2188.8 MHz
- MPERF rate: (0x765f634f828 - 0x3634e64b38) / 3600.0 ≈ 2194.9 MHz

Indeed, both TSC and MPERF rates are very close to the 2.2 GHz reported by CPUID.16H. The small
discrepancy may be due to measurement overhead (system calls to read MSRs). The fixed base frequency
number itself may be a rounded value too.

Now, is the fixed base frequency useful for software? I do not think so. I would argue it is
simply not useful these days.

### Sysfs Base Frequency (Linux Kernel Definition)

The `intel_pstate` Linux kernel driver exposes base frequency in kHz via
`/sys/devices/system/cpu/cpuN/cpufreq/base_frequency`, where `N` is the CPU number. This file exists
only when HWP is enabled, otherwise it is absent. All modern Intel processors support HWP, so unless
it is explicitly disabled with the `intel_pstate=no_hwp` kernel command line option, this file will
be present.

However, this file does not report the same base frequency value as CPUID.16H or
MSR_PLATFORM_INFO. Instead, it reports ACPI CPPC guaranteed performance level converted to
frequency. If ACPI CPPC does not provide the guaranteed performance level, it uses the nominal
performance level instead. If there is no ACPI CPPC data at all, it uses the HWP guaranteed
performance level.

In other words, the algorithm to determine sysfs base frequency is as follows:

1. If ACPI CPPC guaranteed performance level is available:
   - Sysfs base frequency = Guaranteed Performance Level × Scaling Factor
2. Else if ACPI CPPC nominal performance level is available:
   - Sysfs base frequency = Nominal Performance Level × Scaling Factor
3. Else:
   - Sysfs base frequency = HWP Guaranteed Performance Level × Scaling Factor

The CPPC and HWP performance levels are discussed in the [Key CPPC Performance Levels](#key-cppc-performance-levels)
and [Key HWP Performance Levels](#key-hwp-performance-levels) sections. Scaling factor determination
is discussed in the [Performance Level to Frequency Mapping](#performance-level-to-frequency-mapping)
section.

This is a specific algorithm used by the `intel_pstate` driver and not documented or defined
elsewhere. Hence the term "sysfs base frequency" used in this document.

### Sysfs vs Fixed Base Frequency

Let's compare sysfs base frequency and fixed base frequency on the same Raptor Lake system
(Intel Core i5-1340P).

```bash
$ cat /sys/devices/system/cpu/cpu0/acpi_cppc/guaranteed_perf
25
$ cat /sys/devices/system/cpu/cpu0/cpufreq/base_frequency
1900000
$ cat /sys/devices/system/cpu/cpu15/acpi_cppc/guaranteed_perf
14
$ cat /sys/devices/system/cpu/cpu15/cpufreq/base_frequency
1400000
```

The sysfs base frequency differs between P-cores (CPU 0) and E-cores (CPU 15), because they have different
guaranteed performance levels (25 vs. 14). The fixed base frequency is the same for both core types
(2.2 GHz).

Note that the sysfs base frequency is much closer to the traditional meaning of base frequency,
though it is still not a strict guarantee, just a best estimate.

The sysfs base frequency may change dynamically during operation, as the ACPI CPPC guaranteed
performance level may change based on thermal and power conditions, or whether the system is
plugged in or on battery. Server processors come with configurable TDP and SST-PP (Speed Select
Technology - Performance Profile) feature, where users can change TDP or sacrifice some CPU cores to
increase other cores' power budget and lift the guaranteed performance level for the remaining
cores.

These are two completely different values, both referred to as "base frequency". The following
distinction helps avoid confusion:

- **Fixed Base Frequency**: CPUID.16H or MSR_PLATFORM_INFO definition, it is simply the default
  MPERF counter rate, same for all core types, static. Does not represent sustainable frequency.
  Most probably not very useful for software.
- **Sysfs Base Frequency**: Linux kernel definition, derived from ACPI CPPC or HWP guaranteed
  performance level, differs between core types, dynamic. Represents platform best estimate of
  sustainable frequency, but not guaranteed. Depending on thermal and power conditions, the
  workload, other components activity (e.g., GPU), may or may not be sustainable.

Note, however, on older client CPUs (pre-Alder Lake) and server CPUs that support HWP, fixed base
frequency and sysfs base frequency usually yield the same value if features like configurable TDP
did not change it. So in a way, sysfs base frequency can be considered a generalization of fixed
base frequency that works better for modern CPUs and stays closer to the traditional meaning of base
frequency.

### Key Takeaways

1. The "base frequency" term has two completely different meanings for Intel CPUs.
2. **Fixed base frequency**:
   - Obtained via CPUID.16H or MSR_PLATFORM_INFO.
   - Same value for all core types (on hybrid CPUs).
   - Static, never changes.
   - In a default configuration, close to TSC and MPERF counter rate,
   - May not reflect TSC and MPERF rate if the configurable TDP feature is used.
   - Not a guaranteed sustainable frequency.
3. **Sysfs base frequency**:
   - Exposed via `/sys/devices/system/cpu/cpuN/cpufreq/base_frequency`.
   - Derived from ACPI CPPC guaranteed/nominal or HWP guaranteed performance levels.
   - Different values per core type (on hybrid CPUs).
   - Dynamic, can change based on conditions.
   - Represents platform's best estimate of sustainable frequency, but not guaranteed.
4. On non-hybrid CPUs (servers, older clients), both definitions typically yield the same value.

## Conclusions

The term "base frequency" has evolved from a simple, well-understood concept (maximum frequency all
CPU cores could sustain indefinitely with adequate cooling) to a complex and ambiguous term
requiring careful clarification.

Challenges:

- **Two distinct definitions**: Fixed base frequency (SDM) and sysfs base frequency (Linux kernel),
  which differ significantly on hybrid CPUs. In general, sysfs base frequency seems to be more
  useful than fixed base frequency, although the base frequency concept's overall usefulness is
  questionable.
- **Declining relevance**: The "base frequency" concept in general struggles with variable cooling,
  integrated components sharing power budgets, and heterogeneous architectures. Intel has phased out
  base frequency from mobile client CPU specifications and branding strings since Alder Lake (2021).

**Recommendations**:

- For modern Intel CPUs, avoid using "base frequency" when possible, especially for hybrid CPUs.
- When the term must be used, always clarify which definition is meant and whether it represents a
  maximum sustainable frequency in the discussion context.

## Appendix: CPPC vs HWP Performance Levels

This appendix provides detailed data comparing Intel HWP and ACPI CPPC performance levels on
several hybrid Intel client platforms.

**Note**: When ACPI CPPC provides both Nominal and Guaranteed performance levels, they are shown as
"Nominal / Guaranteed" in the tables below.

### Alder Lake

| Performance Level                 | P-core CPPC | P-core HWP | E-core CPPC | E-core HWP |
|-----------------------------------|-------------|------------|-------------|------------|
| Lowest                            | 1           | 1          | 1           | 1          |
| Lowest Nonlinear / Most Efficient | 18          | 21         | 13          | 16         |
| Nominal                           | 26          | 27         | 15          | 15         |
| Highest                           | 60          | 60         | 34          | 34         |

Note: Alder Lake does not have LPE-cores.

### Raptor Lake

| Performance Level                 | P-core CPPC | P-core HWP | E-core CPPC | E-core HWP |
|-----------------------------------|-------------|------------|-------------|------------|
| Lowest                            | 1           | 1          | 1           | 1          |
| Lowest Nonlinear / Most Efficient | 22          | 20         | 16          | 15         |
| Nominal / Guaranteed              | 24 / 25     | 25         | 19 / 14     | 14         |
| Highest                           | 59          | 59         | 34          | 34         |

### Meteor Lake

| Performance Level                 | P-core CPPC | P-core HWP | E-core CPPC | E-core HWP | LPE-core CPPC | LPE-core HWP |
|-----------------------------------|-------------|------------|-------------|------------|---------------|--------------|
| Lowest                            | 1           | 1          | 1           | 1          | 1             | 1            |
| Lowest Nonlinear / Most Efficient | 15          | 15         | 14          | 14         | 11            | 11           |
| Nominal / Guaranteed              | 13 / 14     | 14         | 38 / 7      | 7          | 21 / 4        | 4            |
| Highest                           | 60          | 60         | 38          | 38         | 21            | 21           |

### Arrow Lake

| Performance Level                 | P-core CPPC | P-core HWP | E-core CPPC | E-core HWP | LPE-core CPPC | LPE-core HWP |
|-----------------------------------|-------------|------------|-------------|------------|---------------|--------------|
| Lowest                            | 1           | 1          | 1           | 1          | 1             | 1            |
| Lowest Nonlinear / Most Efficient | 23          | 23         | 16          | 17         | 10            | 9            |
| Nominal / Guaranteed              | 36 / 37     | 37         | 21 / 21     | 21         | 7 / 7         | 7            |
| Highest                           | 72          | 72         | 55          | 55         | 25            | 25           |

### Lunar Lake

| Performance Level                 | P-core CPPC | P-core HWP | LPE-core CPPC | LPE-core HWP |
|-----------------------------------|-------------|------------|---------------|--------------|
| Lowest                            | 1           | 1          | 1             | 1            |
| Lowest Nonlinear / Most Efficient | 19          | 19         | 14            | 19           |
| Nominal / Guaranteed              | 25 / 26     | 26         | 22 / 22       | 22           |
| Highest                           | 55          | 55         | 37            | 37           |

Note: Lunar Lake does not have E-cores.

### Panther Lake

| Performance Level                 | P-core CPPC | P-core HWP | E-core CPPC | E-core HWP | LPE-core CPPC | LPE-core HWP |
|-----------------------------------|-------------|------------|-------------|------------|---------------|--------------|
| Lowest                            | 1           | 1          | 1           | 1          | 1             | 1            |
| Lowest Nonlinear / Most Efficient | 16          | 17         | 15          | 15         | 15            | 9            |
| Nominal                           | 22          | 23         | 16          | 16         | 16            | 16           |
| Highest                           | 36          | 36         | 24          | 24         | 24            | 24           |
