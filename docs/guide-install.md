<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

- Author: Artem Bityutskiy <dedekind1@gmail.com>

# Table of Contents

- [Pepc Packages](#pepc-packages)
- [Using From Source](#using-from-source)
- [Installation Script](#installation-script)
- [Pepc Package Dependencies](#pepc-package-dependencies)
- [Installation Using pip](#installation-using-pip)
- [Using uv](#using-uv)
- [Sudo Complication](#sudo-complication)
- [Tab completions](#tab-completions)
- [Man pages](#man-pages)
- [Example of .bashrc](#example-of-bashrc)

# Pepc Packages

Some Linux distributions provide `pepc` as an installable package. However, these packages are
often outdated. Therefore, it is recommended to install `pepc` using `pip` or `uv` as described
below.

# Using From Source

You can use `pepc` directly from the source code without installation. Clone the repository, change
to the cloned directory, and run `pepc` from there.

```bash
git clone https://github.com/intel/pepc.git
cd pepc
./pepc --help
```

# Installation Script

If you prefer, you can skip reading this guide and use the provided installation script
[`misc/install-pepc.sh`](../misc/install-pepc.sh) to install `pepc`. The script automates the steps
described in this guide and installs `pepc` using the `pip` method.

Script usage examples.

```bash
# Read help message.
install-pepc.sh --help
# Install pepc to the default location (~/.pmtools) from the public repository.
install-pepc.sh
# Same as above, but also install OS package dependencies for Ubuntu.
install-pepc.sh --os-name ubuntu
```

# Pepc Package Dependencies

`pepc` relies on a few system tools and libraries. Ensure the following packages are installed on your
system.

**Fedora / CentOS**

```bash
sudo dnf install -y rsync util-linux procps-ng git
```

**Ubuntu**

```bash
sudo apt install -y rsync util-linux procps git
```

# Installation Using pip

This method installs `pepc` into a Python virtual environment (basically just directory) in your
home directory.

Make sure you have Python `pip3` and `venv` tools installed. To install them, run the following
commands as superuser.

**Fedora / CentOS**

```bash
sudo dnf install python-pip
```

**Ubuntu**

```bash
sudo apt install python3-venv
```

The following installation process does not require superuser privileges.

Install `pepc` and all its Python dependencies into a sub-directory of your choice. Here we use
'~/.pmtools' as an example.

```bash
python3 -m venv ~/.pmtools
~/.pmtools/bin/pip3 install git+https://github.com/intel/pepc.git@release
```

Ensure that '~/.pmtools/bin' is in your 'PATH', add it if necessary.

```bash
export PATH="$PATH:$HOME/.pmtools/bin"
```

# Using uv

`uv` is a modern Python project and package management tool. Many Linux distributions provide a
package for it. For example, in Fedora, run:

```bash
sudo dnf install uv
```

Install `pepc` by running the following command.

```bash
uv tool install git+https://github.com/intel/pepc.git@release
```

`uv` installs projects to '$HOME/.local'. Ensure '$HOME/.local/bin' is in your 'PATH'.

```bash
export PATH="$PATH:$HOME/.local/bin"
```

# Sudo Complication

This section applies to both `pip` and `uv` installation methods.

Unfortunately, running `pepc` with `sudo` works only when you provide the full path to the
executable. This is a standard challenge with using `sudo` and custom 'PATH' settings: `sudo` resets
the 'PATH' variable to a default value for security reasons.

You can use standard methods to overcome this issue. One of them is using a shell alias, for example
in your '~/.bashrc' file:

```bash
alias pepc="sudo PATH=$PATH VIRTUAL_ENV=$HOME/.pmtools $HOME/.pmtools/bin/pepc"
```

With this alias, you can run `pepc` with `sudo` transparently, for example:

```bash
$ pepc pstates info
[sudo] password for user:
Source: Linux sysfs file-system
 - Turbo: on
 - Min. CPU frequency: 800.00MHz for all CPUs
 - Max. CPU frequency: 3.90GHz for all CPUs
... snip ...
```
# Tab completions

`pepc` supports tab completions, but it requires specific environment variables to be set. Run the
following:

```bash
# For pip installation (adjust path if you used a different location):
eval "$($HOME/.pmtools/bin/register-python-argcomplete pepc)"

# For uv installation:
eval "$($HOME/.local/bin/register-python-argcomplete pepc)"
```

Add this line to your '$HOME/.bashrc' file to enable tab completion by default.

# Man pages

`pepc` provides man pages. If you install `pepc` using `pip` or `uv`, the man pages are placed in
Python's 'site-packages' directory, which is not searched by the `man` tool by default. To make
them available, add the `pepc` man page path to your 'MANPATH' environment variable.

Find the man page location with:

```bash
pepc --print-man-path
```

This prints a path like '..../lib/pythonX.Y/site-packages/pepcdata/man'. Add it to 'MANPATH' with:

```bash
export MANPATH="$MANPATH:$(pepc --print-man-path)"
```

Add this line to your '$HOME/.bashrc' to make it persistent.

Verify that man pages are available:

```bash
man pepc-cstates
```

**Note:** `pepc` provides man pages for each subcommand.

# Example of .bashrc

Here is an example of a '$HOME/.bashrc' file that includes the necessary settings for using `pepc`:

```bash
# === pepc settings ===
VENV="$HOME/.pmtools"
VENV_BIN="$VENV/bin"

# Ensure the virtual environment's bin directory is in the PATH.
export PATH="$PATH:$VENV_BIN"

# Convenience alias for running pepc with sudo.
alias pepc="sudo PATH=$PATH VIRTUAL_ENV=$VENV $VENV_BIN/pepc"

# Enable tab completion for pepc.
eval "$($VENV_BIN/register-python-argcomplete pepc)"

# Enable man pages.
export MANPATH="$MANPATH:$($VENV_BIN/pepc --print-man-path)"
# === end of pepc settings ===
```
