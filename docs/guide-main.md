<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Pepc User Guide

- Author: Artem Bityutskiy <dedekind1@gmail.com>

## Table of Contents

- [Introduction](#introduction)
  - [Target CPU Options](#target-cpu-options)
  - [Debug Options](#debug-options)
  - [YAML Output](#yaml-output)
  - [Mechanisms](#mechanisms)
  - [Getting Help](#getting-help)
  - [Superuser Privileges](#superuser-privileges)
  - [Remote Usage Model](#remote-usage-model)
  - [Emulation Data](#emulation-data)
- [P-states](#p-states)
- [C-states](#c-states)
- [Uncore](#uncore)
- [CPU Hotplug](#cpu-hotplug)
- [CPU Topology](#cpu-topology)
- [PM QoS](#pm-qos)
- [TPMI](#tpmi)
- [ASPM](#aspm)

## Introduction

`pepc` command line interface is organized into **commands** and **subcommands**. The
commands are 'pstates', 'cstates', 'tpmi', and so on. Most commands have 'info' (read information)
and 'config' (change configuration) subcommands. However, some commands may have additional or
different subcommands.

### Target CPU Options

By default, most `pepc` commands and subcommands operate on all CPUs. But you can limit the
operation to target CPUs (`--cpus`), cores (`--cores`), modules (`--modules`), dies (`--dies`),
packages (`--packages`) or NUMA nodes (`--nodes`). You can also limit the operation to specific core
siblings (`--core-siblings`) or module siblings (`--module-siblings`).

### Debug Options

When you run into problems using `pepc`, you can enable debug output by adding the `-d` or
`--debug` option to any command. This will print additional debug information that may help
diagnose the problem, or just give you more insight into what `pepc` is doing behind the scenes.

You can limit the debug output to specific Python module names by using
`--debug-modules <module-names>`.

### YAML Output

The 'info' subcommand of most commands supports the `--yaml` option that prints the output in YAML
format, instead of the human-readable format. This is useful for scripting and automated parsing of
the output.

### Mechanisms

`pepc` uses various mechanisms to read and change power management settings. For example,
the 'pepc pstates config --max-freq 2GHz' command changes the maximum CPU frequency using the
'sysfs' mechanism.

Some options support only one mechanism, while others support multiple mechanisms. For example,
the 'pepc uncore info --min-freq' option supports two mechanisms - 'sysfs' and 'tpmi'. By default,
`pepc` tries to use the first mechanism in the list of supported mechanisms, and if it fails, it
tries the next one, and so on.

You can force `pepc` to use a specific mechanism or mechanisms with the
`--mechanisms <mechanism-name>` option. For example, to read the minimum uncore frequency using the
'tpmi' mechanism, use:

```bash
pepc uncore info --min-freq --mechanisms tpmi
```

The list of supported mechanisms for each option is documented in the corresponding manual page.

Some options that sound similar but use different mechanisms are implemented as separate options.
For example, `--cppc-guaranteed-perf` and `--hwp-guaranteed-perf` are implemented as 2 different
options, instead of a single `--guaranteed-perf` option with multiple mechanisms.

What is the criterion? The CPPC guaranteed performance and HWP guaranteed performance have similar
names, but they do not necessarily have the same value. Therefore, they are two separate options.
On the other hand, the 'pepc uncore info --min-freq' option supports both 'sysfs' and 'tpmi'
mechanisms,
because the minimum uncore frequency is supposed to be the same when read via sysfs or TPMI.

**Note:** The difference between CPPC and HWP guaranteed performance levels is explained in the
[Intel CPU Base Frequency Explained](misc-cpu-base-freq.md) article.

### Getting Help

Each command and subcommand supports the `-h` or `--help` option that prints the help text for that
command or subcommand. For example, to get help about the 'pepc pstates config' subcommand, run:

```bash
pepc pstates config --help
```

The help text provides only a brief description of each option. A more detailed description is
available in the man pages. Each command and subcommand has a corresponding man page. Man pages
are written in reStructuredText (rst) format and are located in the [docs/](.) subdirectory of
the `pepc` git repository.

When `pepc` is installed, the 'rst' files are converted into formatted man pages and installed along
with the tool. When `pepc` is configured properly, you can access the man pages with the `man`
command, for example:

```bash
man pepc-uncore
```

Also, remember that there are multiple articles about Linux and Intel CPU power management concepts
in the miscellaneous documentation files in the `pepc` repository.

### Superuser Privileges

Most `pepc` operations require superuser privileges. `pepc` reads from and writes to system
interfaces such as sysfs files (`/sys/...`), MSR device files (`/dev/cpu/*/msr`), and debugfs
files (`/sys/kernel/debug/...`). Writing to these interfaces always requires superuser. Reading
from some of them (for example, MSR device files) also requires superuser.

There are three ways to run `pepc` with superuser privileges.

**1. Run as root**

Install and run `pepc` under the root account. This is straightforward but not how Linux systems
are typically used.

**2. Run as a non-root user with `sudo` rights**

Configure the user account with passwordless `sudo`. `pepc` automatically detects when a
privileged operation is required and retries it via `sudo`. No manual invocation of `sudo` is
necessary.

If passwordless `sudo` is not an option but you want to avoid a password prompt on every
invocation, you can pre-authorize `sudo` once per session using a shell alias:

```bash
alias pepc='sudo -v && pepc'
```

Add this to `~/.bashrc`. `sudo -v` validates (and refreshes if needed) the cached sudo credentials.
If authentication succeeds, `pepc` runs normally. If it fails, `pepc` is not invoked. Within the
`sudo` credential cache window (typically 5–15 minutes), subsequent invocations will not prompt
again.

**3. Run via `sudo`**

Run `pepc` prefixed with `sudo`:

```bash
sudo pepc cstates info
```

This works, but requires some configuration when `pepc` is installed in a Python virtual
environment. By default, `sudo` clears environment variables including `VIRTUAL_ENV`, which breaks
virtual environment activation. There are two ways to address this:

- Add a rule to `/etc/sudoers` that preserves the required environment variables.
- Use a shell alias that passes the variable explicitly:

  ```bash
  alias pepc='sudo VIRTUAL_ENV=/path/to/venv pepc'
  ```

The `tools/install-pepc` script in the `pepc` git repository configures everything necessary
for this scenario automatically. The [installation guide](guide-install.md) covers the details.

### Remote Usage Model

Most people run `pepc` to manage the local system (SUT - System Under Test). However, `pepc` can
also be used to configure remote SUTs over SSH. This is helpful when a single control machine is
used to manage multiple SUTs in a lab environment.

**How remote mode works**

`pepc` remote mode is not the same as SSHing into a SUT and running `pepc` there. Instead, `pepc`
runs entirely on the control machine and connects to the SUT over SSH only to perform individual
operations (for example, to read a sysfs file or write an MSR). This means `pepc` does not need
to be installed on the SUT.

If you do want to install `pepc` on a SUT (for example, to run it in local mode directly on
that system), use the `tools/install-pepc` tool available in the `pepc` git repository. It
installs `pepc` to a remote host from the control machine over SSH.

**SSH Requirements**

The SSH connection to the SUT must satisfy two requirements:

1. **Key-based authentication**: The connection must use key-based authentication without a
   passphrase. Password prompts are not supported.
2. **Superuser privileges**: Many `pepc` operations require superuser privileges on the SUT (for
   example, writing to sysfs or MSR interfaces). This can be satisfied in one of two ways:
   - Log in directly as root.
   - Log in as a non-root user with passwordless `sudo` configured on the SUT. `pepc` automatically
     prepends `sudo` to privileged commands when needed. No manual intervention required.

Use the `-H` option to specify the SUT hostname or IP address, and the `-U` option to specify the
SSH login username. When `-U` is omitted, `pepc` logs in as root.

**Example: root login**

```bash
pepc cstates config -H SUT-name-or-IP --disable C6
```

This logs into 'SUT-name-or-IP' as root over SSH and disables the C6 idle state on that SUT.

**Example: non-root user with passwordless sudo**

```bash
pepc cstates config -H SUT-name-or-IP -U labuser --disable C6
```

`pepc` logs into 'SUT-name-or-IP' as 'labuser'. When a privileged operation is needed (for
example, writing to a sysfs file to disable a C-state), `pepc` automatically prepends `sudo`.

**Convenient lab setup with SSH config**

In a lab with many SUTs, maintaining an `~/.ssh/config` file on the control machine simplifies
things significantly. For example, suppose the SUT named 'ptl' has IP '192.168.10.5', runs Ubuntu,
and has a user 'labuser' with passwordless `sudo`. Add an entry like this to `~/.ssh/config`:

```text
Host ptl
    HostName 192.168.10.5
    User labuser
    IdentityFile ~/.ssh/labkey
```

Now run `pepc` using just the alias:

```bash
pepc cstates config -H ptl --disable C6
```

`pepc` resolves 'ptl' via `~/.ssh/config`, connects as 'labuser' using the specified key, and
automatically uses `sudo` for privileged operations on the SUT. No `-U` or IP address needed on
the command line.

### Emulation Data

The `pepc` tool implements a small abstraction layer that allows running commands on a SUT,
regardless of whether it is local, remote (over SSH), or emulated.

Emulation data is useful for development and testing purposes, because it allows running `pepc`
without real hardware access. Emulation is based on pre-recorded data from real systems.

The `pepc` repository includes emulation data for many types of server and client systems under the
`tests/emul-data/` subdirectory. For example, `tests/emul-data/rpl0` includes emulation data for
a Raptor Lake client system.

To run a `pepc` command on an emulated Raptor Lake system, use the `-D rpl0` option. Keep in
mind, however, that emulation data are not installed along with `pepc`. Therefore, you need to clone
the `pepc` git repository and run `pepc` from there to use emulated SUTs.

Here is an example of running a `pepc` command on an emulated Raptor Lake system:

```bash
./pepc pstates info --max-freq -D rpl0
Max. CPU frequency: 4.60GHz for CPUs 0-7 (P-cores)
Max. CPU frequency: 3.40GHz for CPUs 8-15 (E-cores)
```

The `tools/emulation-data-generator` tool, which is available in the `pepc` git repository,
can be used to collect and save emulation data from a real system. The emulation data should be
placed under the `tests/emul-data/` subdirectory of the `pepc` git repository.

For information on running the `pepc` test suite, see [Pepc Tests Guide](guide-tests.md).

## P-states

The `pepc pstates` command groups operations related to CPU performance states (P-states). This
command is covered in a separate document: [Pepc User Guide: P-states](guide-pstates.md).

## C-states

The `pepc cstates` command groups operations related to CPU idle states (C-states). This command is
covered in a separate document: [Pepc User Guide: C-states](guide-cstates.md).

## Uncore

The `pepc uncore` command groups operations related to CPU uncore, for example reading or changing
uncore performance scaling settings. This command is covered in a separate document:
[Pepc User Guide: Uncore](guide-uncore.md).

## CPU Hotplug

The `pepc cpu-hotplug` command groups operations related to CPU hotplug functionality in Linux.
This command is covered in a separate document:
[Pepc User Guide: CPU Hotplug](guide-cpu-hotplug.md).

## CPU Topology

The `pepc topology` command groups operations related to CPU topology, including non-compute die
details. This command is covered in a separate document:
[Pepc User Guide: Topology](guide-topology.md).

## PM QoS

The `pepc pmqos` command groups operations related to Linux PM QoS (Power Management Quality of
Service) settings. This command is covered in a separate document:
[Pepc User Guide: PM QoS](guide-pmqos.md).

## TPMI

The `pepc tpmi` command groups operations related to TPMI. This command is covered in a separate
document: [Pepc User Guide: TPMI](guide-tpmi.md).

## ASPM

The `pepc aspm` command groups operations related to PCI Express Active State Power Management
(ASPM). This command is covered in a separate document:
[Pepc User Guide: ASPM](guide-aspm.md).
