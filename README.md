<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

Document author: Artem Bityutskiy <dedekind1@gmail.com>

- [Introduction](#introduction)
  - [Context](#context)
- [Authors and contributors](#authors-and-contributors)
- [What is supported](#what-is-supported)
- [Requirements](#requirements)
- [Installation](#installation)
- [Examples](#examples)
- [Helpful resources](#helpful-resources)
- [FAQ](#faq)

# Introduction

Pepc, short for "Power, Energy, and Performance Configurator", is a command-line tool designed for
managing and optimizing CPU power management features.

**IMPORTANT**: This tool is intended for debugging and research purposes only. It requires root
permissions and should only be used in a lab environment, not in production.

## Context

There are numerous Linux tools for power management configuration. This section explains why we
created another one.

We work on power and performance, including measuring C-state latencies using
[wult](https://github.com/intel/wult) and collecting power and performance statistics using
[stats-collect](https://github.com/intel/stats-collect). We frequently configure power and
performance  settings, such as enabling/disabling C-states, limiting CPU/uncore frequency,
or tweaking features like C1 demotion, among others.

Before pepc, we relied on multiple tools like cpupower and lscpu, and memorized sysfs paths for
various settings, such as disabling a C-state. This approach was cumbersome and error-prone. It
lacked flexibility; for instance, disabling C1 for a single CPU module required identifying the
CPU numbers in that module and disabling C1 for each CPU individually. Additionally, configuring
hardware features like C1 demotion required knowledge of MSR registers and specific bit toggles.
While tools like wrmsr and rdmsr were useful, they were not user-friendly for frequent use.

Pepc simplifies power and performance configuration by eliminating the need to remember sysfs paths
and platform-specific MSR numbers. It is flexible, supports various CPU models, well-structured,
and offers a Python API for integration with other Python projects.

# Authors and contributors

* Artem Bityutskiy <dedekind1@gmail.com> - original author, project maintainer.
* Antti Laakso <antti.laakso@linux.intel.com> - contributor, project maintainer.
* Niklas Neronin <niklas.neronin@intel.com> - contributor.
* Adam Hawley <adam.james.hawley@intel.com> - contributor.
* Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com> - contributor.
* Juha Haapakorpi <juha.haapakorpi@intel.com> - contributor.
* Tero Kristo <tero.kristo@gmail.com>> - contributor.

# What is supported

Pepc supports discovering and configuring the following features.
* C-states: [documentation](docs/pepc-cstates.rst)
* P-states: [documentation](docs/pepc-pstates.rst)
* PM QoS: [documentation](docs/pepc-pmqos.rst)
* CPU onlining and offlining: [documentation](docs/pepc-cpu-hotplug.rst)
* ASPM: [documentation](docs/pepc-aspm.rst)
* CPU topology: [documentation](docs/pepc-topology.rst)
* TPMI: [documentation](docs/pepc-tpmi.rst)

Some features are hardware-agnostic, while others depend on specific hardware capabilities.

# Requirements

* Pepc requires Python 3.9 or newer.
* Run pepc as a superuser (e.g., using "sudo").
* Many options need access to MSRs (Model Specific Registers), requiring the "msr" kernel driver
  Ensure the "msr" kernel driver is available, as some Linux distributions may disable it by
  default.

# Installation

Please, refer to the [installation guide](docs/guide-install.md) document.

# Examples

Please, refer to the [usage examples](docs/guide-examples.md) document.

# Helpful resources

* A document describing Intel C-state namespaces: [here](docs/misc-cstate-namespaces.md).
* A document explaining MSR scope and how pepc simplifies understanding a complex processor
  configuration: [here](doc/misc-msr-scope.md).

# FAQ

## What to do if my platform is not supported?

Some pepc features (e.g., --pkg-cstate-limit) are implemented only for certain Intel platforms.
This does not necessarily mean that the feature is not supported by other platforms, it only means
that we verified it on a limited amount of platforms. Just to be on a safe side, we refuse changing
the underlying MSR registers on platforms we did not verify.

If pepc fails with a message like "this feature is not supported on this platform" for you, feel
free to contact the authors with a request. Very often it ends up with just adding a CPU ID to the
list of supported platforms, and may be you can do it yourself and submit a patch/pull request.
