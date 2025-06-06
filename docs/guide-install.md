<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
-->

Document author: Artem Bityutskiy <dedekind1@gmail.com>

- [Introduction](#introduction)
  - [Dependencies](#dependencies)
    - [Fedora](#fedora-1)
    - [Ubuntu](#ubuntu)
  - [Using uv](#using-uv)
  - [Using pip](#using-pip)
  - [Fedora](#fedora)
  - [CentOS 9 Stream](#centos-9-stream)
  - [Standalone version](#standalone-version)
  - [Tab completions](#tab-completions)
  - [Man pages](#man-pages)
  - [Example of .bashrc](#example-of-bashrc)

# Introduction

This document provides a guide for installing the `pepc` tool.

**IMPORTANT**: This tool is intended for debugging and research purposes only. It requires root
permissions and should only be used in a lab environment, not in production.


## Dependencies

Pepc requires certain system tools and libraries. Below are the installation instructions.

### Fedora

```
sudo dnf install -y rsync util-linux procps-ng
```

### Ubuntu

```
sudo apt install -y rsync util-linux procps
```

## Using uv

Uv is a modern Python project and package management tool. Install it on your system. Many Linux
distributions provide a package for it. Also install git. For example, in Fedora, run:

```
sudo dnf install uv git
```

Install pepc by running the following command.

```
uv tool install git+https://github.com/intel/pepc.git@release
```

uv installs projects to '$HOME/.local'. Ensure '$HOME/.local/bin' is in your 'PATH'.

```
$ which pepc
~/.local/bin/pepc
```

If you installed pepc as root and plan to use pepc as root, no additional steps are required.

### sudo complication

Unfortunately, running pepc with sudo works only when you provide the full path to the executable.

```
sudo ~/.local/bin/pepc --version
1.5.32
```

Using only the command name causes an error.

```
sudo pepc
sudo: pepc: command not found
```

To overcome this, create an alias as shown below and add it to your `$HOME/.bashrc` file:

```
alias pepc="sudo $HOME/.local/bin/pepc"
```
You can now run `pepc` directly. For example:

```
pepc pstates info
[sudo] password for user:
Source: Linux sysfs file-system
 - Turbo: on
 - Min. CPU frequency: 800.00MHz for all CPUs
... snip ...
```

## Using pip

Install pip and python virtualenv on your system. Most modern Linux distributions include a package
for this. Also install git. For example, in Fedora, run

```
dnf install python-pip git
```

In Ubuntu, run

```
apt install python3-venv git
```

Install pepc into a python virtual environment using the following commands.

```
python3 -m venv ~/.pmtools
~/.pmtools/bin/pip3 install git+https://github.com/intel/pepc.git@release
```

Ensure that '$HOME/.pmtools/bin' is in your 'PATH'. Verify this as follows.

```
$ which pepc
~/.pmtools/bin/pepc
```

If you installed pepc as root and plan to use pepc as root, no additional steps are required.

### sudo complication

Similar to the "using uv" case, create an alias and add it to your `$HOME/.bashrc` file as shown below:

```
alias pepc="sudo VIRTUAL_ENV=$HOME/.pmtools $HOME/.pmtools/bin/pepc"
```

## Fedora

Pepc is available in Fedora starting from version 38. However, Fedora packages may not provide the
latest version. To install the latest release, use the "uv" or "pip" methods.

To install pepc, run:

```
sudo dnf install pepc
```

Fedora packages are maintained by Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com>.

## CentOS 9 Stream

Pepc is available for CentOS 8 Stream via the EPEL repository. Note that EPEL packages may not
always provide the latest version. To get the latest release, consider using the "uv" or "pip"
installation methods.

To add EPEL and install Pepc, follow these steps:

```
sudo dnf install epel-release
sudo dnf install pepc
```

Epel packages are maintained by Ali Erdinç Köroğlu <ali.erdinc.koroglu@intel.com>.

## Standalone version

To create a standalone version of pepc, ensure your Python version is greater than 3.8.
Run the following command, which should print "Good" if the version is compatible:

```
/usr/bin/python3 -c 'import sys; ver=sys.version_info; \
print("Good") if ver.major > 2 and ver.minor > 8 else print("Bad")'
```

Create the standalone version of pepc.

```
git clone https://github.com/intel/pepc.git --branch release pepc
cd pepc
echo '#!/usr/bin/python3' > pepc.standalone
git archive --format zip HEAD >> pepc.standalone
chmod ug+x pepc.standalone
```
This creates the 'pepc.standalone' file, which you can rename and copy anywhere for standalone use.

## Tab completions

Pepc supports tab completions, but it requires specific environment variables to be set. Make sure
'pepc' is in your '$PATH', and  use the following:

```
# Assuming pepc was installed to '$HOME/.pmtools'.
eval "$($HOME/.pmtools/bin/register-python-argcomplete pepc)"
```

Add this line to '$HOME/.bashrc' file to enable tab completion by default.

## Man pages

Pepc provides man pages. If you install pepc using 'pip' or 'uv', the man pages are placed in
Python's "site-packages" directory, which is not searched by the "man" tool by default. To make
them available, add the pepc man page path to your 'MANPATH' environment variable.

Find the man page location with:

```
pepc --print-man-path
```

This prints a path like '..../lib/pythonX.Y/site-packages/pepcdata/man'. Add it to 'MANPATH' with:

```
export MANPATH="$MANPATH:$(pepc --print-man-path)"
```

Add this line to your '$HOME/.bashrc' to make it persistent.

Verify that man pages are available:

```
man pepc-cstates
```

Note: Pepc provides man pages for each subcommand.

## Example of .bashrc

Here is an example of a `$HOME/.bashrc` file that includes the necessary settings for using pepc:

```
# Change the path if you installed pepc to a different location.
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
```
