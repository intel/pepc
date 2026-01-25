<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

- Author: Artem Bityutskiy \<dedekind1@gmail.com\>

# Table of Contents

- [Introduction](#introduction)
- [Disclaimer](#disclaimer)
- [Privileges](#privileges)
- [Requirements](#requirements)
- [Installation](#installation)
- [User Guide](#user-guide)
- [Man pages](#man-pages)
- [Helpful resources](#helpful-resources)
- [Remote Usage Model](#remote-usage-model)
- [SUT emulation](#sut-emulation)
- [FAQ](#faq)

# Introduction

`pepc`, short for "Power, Energy, and Performance Configurator", is a command-line tool designed for
reading and changing power management features. For example, `pepc` can be used to modify CPU
or uncore frequency limits for all or a subset of CPUs, cores, modules, dies, or packages in the
system.

`pepc` consolidates power management configuration in one tool with a consistent and convenient
command-line interface instead of using various tools, such as `cpupower`, `rdmsr`,
`cat /sys/...`, etc.

# Disclaimer

This is not an official Intel product. It is an open-source tool developed by Intel engineers to
facilitate power and performance configuration in Linux in lab environments. Please use it
at your own risk.

# Privileges

Some `pepc` read operations may be done without superuser privileges, some require superuser
privileges (root). This depends on the specific operation and the underlying mechanism. For example,
reading CPU frequency limits from sysfs does not need root, therefore `pepc pstates info --min-freq`
can be run as a normal user. On the other hand, reading an MSR (Model Specific Register) needs
superuser privileges, so something like `pepc cstates info --pkg-cstate-limit` needs to be run as
root.

# Requirements

* `pepc` requires Python 3.9 or newer.
* Many options need access to MSRs (Model Specific Registers), requiring the `msr` kernel driver.
  Ensure the `msr` kernel driver is available, as some Linux distributions may disable it by
  default.

# Installation

Please refer to the [Installation Guide](docs/guide-install.md) document.

# User Guide

Please refer to the [User Guide](docs/guide-main.md) document.

# Man pages

Here are the manual pages for all `pepc` features. They are also installed along with `pepc` and can be
accessed via the `man` command (e.g., `man pepc-cstates`).
- CPU C-states: [man page](docs/pepc-cstates.rst)
- CPU P-states: [man page](docs/pepc-pstates.rst)
- Uncore properties: [man page](docs/pepc-uncore.rst)
- PM QoS: [man page](docs/pepc-pmqos.rst)
- ASPM: [man page](docs/pepc-aspm.rst)
- CPU onlining and offlining: [man page](docs/pepc-cpu-hotplug.rst)
- CPU topology: [man page](docs/pepc-topology.rst)
- TPMI: [man page](docs/pepc-tpmi.rst)

Some features are hardware-agnostic, while others depend on specific hardware capabilities.

# Helpful resources

- [Intel CPU Base Frequency Explained](docs/misc-cpu-base-freq.md) - explains the concept of CPU base
  frequency and many CPU performance scaling topics.
- [Intel C-state namespaces](docs/misc-cstate-namespaces.md) - explains C-state naming conventions.
- [Xeon C6P and C6SP Idle States](docs/misc-c6p-c6sp.md) - explains the C6P and C6SP idle states on
  Intel Xeon platforms.
- [Uncore ELC and Frequency Scaling](docs/misc-uncore-elc.md) - explains the uncore ELC mechanism.
- [MSR scope](docs/misc-msr-scope.md) - explains the concept of MSR scope (per-core, per-module,
  per-package) and related pitfalls.

The following articles are not directly related to `pepc`, but may be helpful to understand some of
the features `pepc` manages.
- [Measured CPU Frequency and C-states](docs/misc-c1e-cpu-freq.md) - explains why measured CPU
  frequency may be lower than expected when C1E or deeper C-states are enabled.
- [TSC, APERF, and MPERF Counters](docs/misc-tsc-amperf.md) - explains the TSC, APERF, and MPERF
  counters and their interaction.

# FAQ

## What to do if my platform is not supported?

Some `pepc` features (e.g., `--pkg-cstate-limit`) are implemented only for certain Intel platforms.
This means that we verified the feature on a limited number of platforms, not that it is
unsupported by other platforms. To be on the safe side, we refuse to change the underlying MSR
registers on platforms we did not verify.

If `pepc` fails with a message like "this feature is not supported on this platform" for you, feel
free to contact the authors with a request. Often this can be resolved by simply adding a CPU ID to the
list of supported platforms, and you may be able to do this yourself and send a pull request.
