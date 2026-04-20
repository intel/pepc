<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

# Installation Guide

- Author: Artem Bityutskiy <dedekind1@gmail.com>

## Table of Contents

- [Pepc Packages](#pepc-packages)
- [Running From Source](#running-from-source)
- [Installation Script](#installation-script)
- [Standalone Executable](#standalone-executable)
- [Manual Installation](#manual-installation)
  - [Pepc Package Dependencies](#pepc-package-dependencies)
  - [Installation Using pip](#installation-using-pip)
  - [Using uv](#using-uv)
  - [Sudo Configuration](#sudo-configuration)
  - [Tab completions](#tab-completions)
  - [Man pages](#man-pages)
  - [Example of .bashrc](#example-of-bashrc)

## Pepc Packages

Some Linux distributions provide `pepc` as an installable package. However, these packages are
out of date, do not use them.

## Running From Source

You can run `pepc` directly from the source code without installation. Clone the repository, change
to the cloned directory, and run `pepc` from there.

```bash
git clone https://github.com/intel/pepc.git
cd pepc
./pepc --help
```

This method is not recommended for regular use. For regular use, a proper installation is
recommended: it configures shell tab completions and man pages, so commands like
`man pepc-cstates` work out of the box.

## Installation Script

The `tools/install-pepc` script is the simplest way to install `pepc`. It takes care of
everything: installing OS dependencies, creating the Python virtual environment, configuring
shell tab completions, man pages, and adding a `sudo` alias if needed.

Clone the repository to get the installation script:

```bash
git clone https://github.com/intel/pepc.git
cd pepc
```

**Install the latest release from GitHub**

Run `tools/install-pepc` without arguments. It fetches and installs the latest `pepc` release
directly from GitHub. The local clone is only used to run the script.

```bash
./tools/install-pepc
```

**Install from a local clone**

Use `--src-path` to install from the local clone instead.

```bash
./tools/install-pepc --src-path .
```

The script adds `pepc` configuration to your `~/.bashrc`. Re-login or source `~/.bashrc` to apply
the changes.

```bash
. ~/.bashrc
```

`tools/install-pepc` has additional options to tune the installation (e.g. the installation
path), install `pepc` on a remote host over SSH, and control `sudo` alias creation and style.
See [guide-main.md](guide-main.md) for a discussion of `sudo` usage with `pepc`. Run
`./tools/install-pepc --help` to see all available options.

## Standalone Executable

The `tools/make-standalone` script creates a standalone `pepc` zipapp: a single self-contained
executable file that bundles `pepc` and all its Python dependencies. No installation, virtual
environment, or `PATH` changes are required to run it.

This is useful when you want to copy `pepc` to a machine without setting up a Python environment,
or when you want a portable snapshot of a specific `pepc` version.

Like running from source, the standalone executable does not configure shell tab completions or man
pages, so `man pepc-cstates` and tab completion will not work. It is best suited for short-term or
one-off use. For regular use, a proper installation is recommended.

Clone the repository and run `tools/make-standalone` to create the executable.

```bash
git clone https://github.com/intel/pepc.git
cd pepc
./tools/make-standalone
```

This produces a `pepc-standalone` file in the current directory. Copy it to the target machine
and run it directly.

```bash
./pepc-standalone --help
```

`tools/make-standalone` accepts the same `--src-path` option as `tools/install-pepc`, so you can
build a standalone from a local clone or a specific Git URL. Run `./tools/make-standalone --help`
for all options.

## Manual Installation

The following sections describe how to install `pepc` manually, without using the `tools/install-pepc`
script. This is useful if you want full control over the installation, use a custom environment, or
prefer a different package manager.

### Pepc Package Dependencies

`pepc` requires a few OS packages. Most are typically pre-installed, but verify they are present on
your system.

**Tools used by `pepc` at runtime:**

- `cat`, `id`, `uname` from the `coreutils` package.
- `dmesg` from the `util-linux` package, to read kernel messages for improved error reporting.
- `modprobe` from the `kmod` package, to load kernel modules such as `msr`.

**Tools needed for installation:**

- `pip3` and `virtualenv`: required for `pip`-based installation
   (see [Installation Using pip](#installation-using-pip)).
- `uv`: an alternative to `pip3` + `virtualenv` (see [Using uv](#using-uv)). Install one or the other.
- `rsync`: used to copy sources to a temporary directory during installation from a local path.

The commands below install the `pip3`-based tools. If you prefer `uv`, install it instead and skip
`python3-pip` and `python3-virtualenv`.

**Fedora / CentOS**

```bash
sudo dnf install -y util-linux kmod python3-pip python3-virtualenv rsync
```

**Ubuntu**

```bash
sudo apt install -y util-linux kmod python3-pip python3-venv rsync
```

### Installation Using pip

This method installs `pepc` into a Python virtual environment in your home directory. The
installation does not require superuser privileges.

Install `pepc` and all its Python dependencies into a directory of your choice. The example below
uses `~/.pmtools`.

```bash
python3 -m venv ~/.pmtools
~/.pmtools/bin/pip3 install git+https://github.com/intel/pepc.git@release
```

Ensure that `~/.pmtools/bin` is in your `PATH`. Add the following line to your `~/.bashrc` to make
it persistent.

```bash
export PATH="$PATH:$HOME/.pmtools/bin"
```

### Using uv

`uv` is a modern Python project and package manager. Install it using your distribution's package
manager. For example, on Fedora:

```bash
sudo dnf install uv
```

Install `pepc` by running:

```bash
uv tool install git+https://github.com/intel/pepc.git@release
```

`uv` installs tools to `$HOME/.local/bin`. Add the following line to your `~/.bashrc` to ensure
`pepc` is found.

```bash
export PATH="$PATH:$HOME/.local/bin"
```

### Sudo Configuration

Many `pepc` operations require superuser privileges. When `pepc` is installed in a Python virtual
environment, running it with `sudo` requires extra configuration: `sudo` resets `PATH` and
environment variables, which breaks virtual environment activation.

See the [Superuser Privileges](guide-main.md#superuser-privileges) section in the main guide for a
full background and discussion. Two `~/.bashrc` snippets are provided below for quick reference.

**Option 1: refresh**

The alias pre-authorizes `sudo` credentials before invoking `pepc`. Requires passwordless `sudo`
or prompts once per session.

```bash
alias pepc='sudo -v && pepc'
```

**Option 2: wrap**

The alias passes the virtual environment variables to `sudo` explicitly.

```bash
VENV="$HOME/.pmtools"
VENV_BIN="$VENV/bin"
alias pepc="sudo PATH=$PATH VIRTUAL_ENV=$VENV $VENV_BIN/pepc"
```

### Tab completions

`pepc` supports tab completions. Add one of the following lines to `~/.bashrc`, depending on how
`pepc` was installed.

```bash
# For pip installation (adjust path if you used a different location):
eval "$($HOME/.pmtools/bin/register-python-argcomplete pepc)"

# For uv installation:
eval "$($HOME/.local/bin/register-python-argcomplete pepc)"
```

### Man pages

`pepc` provides man pages for each subcommand (e.g., `man pepc-cstates`). When installed via `pip`
or `uv`, the man pages land in Python's `site-packages` directory, which `man` does not search by
default. Add the following line to `~/.bashrc` to make them available.

```bash
export MANPATH="$MANPATH:$(pepc --print-man-path)"
```

Verify with:

```bash
man pepc-cstates
```

### Example of .bashrc

The example below is for a `pip`-based installation into `~/.pmtools`, using the `refresh` sudo
approach. Adjust paths and the sudo alias as needed for your setup.

```bash
# === pepc settings ===
VENV="$HOME/.pmtools"
VENV_BIN="$VENV/bin"

# Ensure the virtual environment's bin directory is in the PATH.
export PATH="$PATH:$VENV_BIN"

# Sudo alias: pre-authorizes sudo credentials before invoking pepc.
alias pepc='sudo -v && pepc'

# Enable tab completion for pepc.
eval "$($VENV_BIN/register-python-argcomplete pepc)"

# Enable man pages.
export MANPATH="$MANPATH:$($VENV_BIN/pepc --print-man-path)"
# === end of pepc settings ===
```
