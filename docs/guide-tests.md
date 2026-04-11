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
- [Running Tests](#running-tests)
  - [Against Emulated Hosts](#against-emulated-hosts)
  - [Against a Local Host](#against-a-local-host)
  - [Against a Remote Host](#against-a-remote-host)
- [Local-only Tests](#local-only-tests)
- [Debug Messages](#debug-messages)
- [Special Dataset Notes](#special-dataset-notes)

## Overview

Most `pepc` tests can run against three kinds of systems: emulated hosts, the local host, or a
remote host over SSH. The default mode is emulation.

Emulation is based on pre-recorded data from real systems. The `pepc` repository includes emulation
datasets in the `tests/emul-data/` subdirectory, one per recorded system. For general
information about emulation and the `-D` option, refer to the
[Pepc User Guide: Emulation Data](guide-main.md#emulation-data) section.

## Running Tests

**Warning:** tests that run against a real host (local or remote) change power management settings,
take CPUs offline, and otherwise actively modify system state. Only run them on a dedicated lab
machine, never on a production system.

### Against Emulated Hosts

By default, running `pytest` runs the tests against all available emulation datasets. Running all
datasets takes a long time, so running tests in parallel with the `-n` option of `pytest-xdist` is
recommended:

```bash
pytest -n 8
```

Do not use too many parallel workers. Each worker creates temporary files in `/tmp` for emulation,
so with too many workers the tests may fail with I/O errors or run out of space. `-n 8` is a
reasonable default. Do not exceed the number of CPUs on the machine.

To run against a single dataset, use the `-D` option:

```bash
pytest -D spr0
```

To list available datasets, look in the `tests/emul-data/` directory.

### Against a Local Host

To run tests on the local host instead of emulation, pass `localhost` as the hostname:

```bash
pytest -H localhost
```

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

## Local-only Tests

A small number of test modules do not support emulation. They run only against the local or remote
host:

- `test_process_manager.py`
- `test_python_prj_installer.py`

These tests are skipped automatically when running in emulation mode.

## Debug Messages

To enable debug log output during a test run, use `--log-cli-level`:

```bash
pytest --log-cli-level=DEBUG
```

To disable stdout/stderr capturing and see all output written to stdout/stderr directly on the console:

```bash
pytest -s
```

## Special Dataset Notes

Some datasets record systems with non-default kernel boot parameters that affect test behavior:

- `spr-nomwait`: has the `idle=nomwait` boot parameter.
- `bdwex0-nocpuidle`: has the `cpuidle.off=1` boot parameter.
