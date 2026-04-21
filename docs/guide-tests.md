<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Pepc Tests Guide

- Author: Artem Bityutskiy <dedekind1@gmail.com>

## Table of Contents

- [Overview](#overview)
- [Test Categories](#test-categories)
- [Running Tests](#running-tests)
  - [Default: Emulation](#default-emulation)
  - [All Emulation Datasets](#all-emulation-datasets)
  - [Specific Emulation Dataset](#specific-emulation-dataset)
  - [Against a Local Host](#against-a-local-host)
  - [Against a Remote Host](#against-a-remote-host)
  - [Combining a Real Host and Emulation](#combining-a-real-host-and-emulation)
- [Real-Host-Only Tests](#real-host-only-tests)
- [Debug Messages](#debug-messages)
- [Special Dataset Notes](#special-dataset-notes)

## Overview

`Pepc` tests are organized into three categories based on what execution targets they support:
emulated hosts, the local host, or a remote host over SSH. The default target is emulation.

Emulation is based on pre-recorded data from real systems. The `pepc` repository includes emulation
datasets in the `tests/emul-data/` subdirectory, one per recorded system. For general information
about emulation and the `-D` option, refer to the
[Pepc User Guide: Emulation Data](guide-main.md#emulation-data) section.

The execution policy is centralized in `tests/conftest.py`, which documents the full set of rules
and the meaning of every option combination.

## Test Categories

Tests fall into three categories that determine where and how they run.

**Host-independent tests** run locally, but neither depend on host-specific hardware state nor
modify system configuration. Examples: `test_yaml.py`, `test_human.py`. These tests always run
exactly once regardless of `-H` or `-D`.

**Emulation-capable tests** need host capabilities such as C-states, P-states, or ASPM, but can
satisfy those needs either from a real host or from an emulation dataset. Examples:
`test_cstates_cmdl.py`, `test_aspm_cmdl.py`. These are the tests that `-H` and `-D` control.

**Real-host-only tests** need a real host and cannot run on emulation. Examples:
`test_process_manager.py`, `test_python_prj_installer.py`. These tests run on the local host by
default and are skipped when an emulation dataset is requested without a real host.

## Running Tests

**Warning:** tests that run against a real host (local or remote) change power management settings,
take CPUs offline, and otherwise actively modify system state. Only run them on a dedicated lab
machine, never on a production system.

### Default: Emulation

Running `pytest` with no options uses the default dataset selection policy. For most
emulation-capable tests this means all available datasets, but some tests run on a smaller
representative set when broader coverage adds little value. See `_DEFAULT_DATASETS` in
`tests/conftest.py` for the current per-test overrides.

Running all datasets takes a long time, so parallel execution with `pytest-xdist` is recommended:

```bash
pytest -n 8
```

Do not use too many parallel workers. Each worker creates temporary files in `/tmp` for emulation,
so with too many workers the tests may fail with I/O errors or run out of space. `-n 8` is a
reasonable default. Do not exceed the number of CPUs on the machine.

### All Emulation Datasets

To force all emulation-capable tests to run on every available dataset regardless of any per-test
default, use `-D all`:

```bash
pytest -D all
pytest -n 8 -D all
```

### Specific Emulation Dataset

To run against a single named dataset:

```bash
pytest -D spr0
```

To list available datasets, look in the `tests/emul-data/` directory.

### Against a Local Host

To run tests on the local host instead of emulation, pass `localhost` as the hostname:

```bash
pytest -H localhost
```

Without root access or passwordless sudo, many host-dependent tests will fail due to insufficient
permissions.

Do not use `-n` for parallel execution against a real host, as tests will interfere with each
other by modifying shared system state.

### Against a Remote Host

To run tests on a remote host over SSH:

```bash
pytest -H my-server
pytest -H my-server -U username
```

The hostname is resolved using SSH configuration files (`~/.ssh/config`), so user name, SSH key,
port, and other settings defined there are picked up automatically. The `-U` option overrides the
user name if needed.

Do not use `-n` for parallel execution against a real host.

### Combining a Real Host and Emulation

For emulation-capable tests, `-H` and `-D` can be combined. The test runs on the real host and
also on the specified emulation dataset selection in the same pytest session:

```bash
# Run on my-server and also on the cpx0 emulation dataset.
pytest -H my-server -D cpx0

# Run on my-server and also on all emulation datasets.
pytest -H my-server -D all
```

This is useful for comparing real-host behavior against emulation in a single run.

For real-host-only tests `-D` is silently ignored when `-H` is also provided, because those tests
never run on emulation.

## Real-Host-Only Tests

The following test modules require a real host and cannot run on emulation:

- `test_process_manager.py`
- `test_python_prj_installer.py`

When no `-H` option is given, these tests run on `localhost` by default. When `-D` is given
without `-H`, these tests are skipped.

## Debug Messages

To enable debug log output during a test run, use `--log-cli-level`:

```bash
pytest --log-cli-level=DEBUG
```

To disable stdout/stderr capturing and see all output written to stdout/stderr directly on the
console:

```bash
pytest -s
```

## Special Dataset Notes

Some datasets record systems with non-default kernel boot parameters that affect test behavior:

- `spr-nomwait`: has the `idle=nomwait` boot parameter.
- `bdwex0-nocpuidle`: has the `cpuidle.off=1` boot parameter.
