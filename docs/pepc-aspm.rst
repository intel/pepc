.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: ASPM

.. Contents::
   :depth: 2
..

================
Command *'aspm'*
================

General options
===============

**-h**
   Show a short help message and exit.

**-q**
   Be quiet (print only improtant messages like warnings).

**-d**
   Print debugging information.

**--debug-modules** *MODNAME[,MODNAME1,...]*
   While the '-d' option enables all debug messages, this option limits them to the specified
   modules. For example, '-d --debug-modules MSR' will only show debug messages from the 'MSR'
   module.

**--version**
   Print the version number and exit.

**-H** *HOSTNAME*, **--host** *HOSTNAME*
   Host name or IP address of the target system. The pepc command will be executed on this system
   using SSH, instead of running it locally. If not specified, the command will be run locally.

**-U** *USERNAME*, **--username** *USERNAME*
   Username for SSH login to the remote host. Defaults to 'root'.

**-K** *PRIVKEY*, **--priv-key** *PRIVKEY*
   Path to the private SSH key for logging into the remote host. Defaults to keys in standard paths
   like '$HOME/.ssh'.

**-T** *TIMEOUT*, **--timeout** *TIMEOUT*
   Timeout for establishing an SSH connection in seconds. Defaults to 8.

**-D** *DATASET*, **--dataset** *DATASET*
   This option is for debugging and testing. It specifies the dataset to emulate a host for running
   the command. Typically used when running 'pepc' from the source directory, which includes datasets
   for various systems.

   The argument can be a dataset path or name. If specified by name, the following locations are
   searched for the dataset.

   1. './tests/data' in the program's directory
   2. '$PEPC_DATA_PATH/tests/data'
   3. '$HOME/.local/share/pepc/tests/data'
   4. '$VIRTUAL_ENV/share/tests/data'
   5. '/usr/local/share/pepc/tests/data'
   6. '/usr/share/pepc/tests/data'

**--force-color**
   Force colorized output even if the output stream is not a terminal (adds ANSI escape codes).

**--print-man-path**
  Print path to pepc manual pages directory and exit. This path can be added to the 'MANPATH'
  environment variable to make the manual pages available to the 'man' tool.

Subcommand *'info'*
===================

Get information about current PCI ASPM configuration.

**--policy** *NAME*
   Display the current global PCI ASPM policy from
   '/sys/module/pcie_aspm/parameters/policy'. The "default" policy indicates the system's default.

**--policies** *NAME*
   List available PCI ASPM policies from '/sys/module/pcie_aspm/parameters/policy'.

**--device** *ADDR*
   Specify the PCI device address for the '--l1-aspm' option. Example: '0000:00:02.0'.

**--l1-aspm**
   Retrieve the L1 ASPM status (on/off) for the PCI device specified by '--device'. Reads from
  '/sys/bus/pci/devices/{device}/link/l1_aspm'.

Subcommand *'config'*
=====================

Change PCI ASPM configuration.

**--policy** *NAME*
   Set the global PCI ASPM policy by writing to '/sys/module/pcie_aspm/parameters/policy'. Use
   "default" to reset the policy to the system's default setting.

**--device** *ADDR*
   Specify the PCI device address for the '--l1-aspm' option. Example: '0000:00:02.0'.

**--l1-aspm** *OPTION*
   Enable or disable L1 ASPM for the PCI device specified by '--device'. This is done via
   '/sys/bus/pci/devices/{device}/link/l1_aspm'. Valid values are 'on', 'off', 'enable', 'disable',
   'true', or 'false'.
