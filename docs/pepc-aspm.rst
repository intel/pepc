.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Date:   09-03-2023
:Title:  ASPM

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
   Be quiet.

**-d**
   Print debugging information.

**--version**
   Print version and exit.

**-H** *HOSTNAME*, **--host** *HOSTNAME*
   Name of the host to run the command on.

**-U** *USERNAME*, **--username** *USERNAME*
   Name of the user to use for logging into the remote host over SSH. The default user name is
   'root'.

**-K** *PRIVKEY*, **--priv-key** *PRIVKEY*
   Path to the private SSH key that should be used for logging into the remote host. By default the
   key is automatically found from standard paths like '$HOME/.ssh'.

**-T** *TIMEOUT*, **--timeout** *TIMEOUT*
   SSH connection timeout in seconds, default is 8.

**-D** *DATASET*, **--dataset** *DATASET*
   This option is for debugging and testing purposes only, it defines the dataset that will be used
   to emulate a host for running the command on. This option is typically used when running 'pepc'
   from the source code directory, which includes datasets for many different systems.

   The argument can be the dataset path, 'all' to specify all available dataset or name in which
   case the following locations will be searched for.

   1. './tests/data', in the directory of the running program
   2. '$PEPC_DATA_PATH/tests/data'
   3. '$HOME/.local/share/pepc/tests/data'
   4. '/usr/local/share/pepc/tests/data'
   5. '/usr/share/pepc/tests/data'

**--force-color**
   Force coloring of the text output.

Subcommand *'info'*
===================

Get information about current PCI ASPM configuration.

**--policy** *NAME*
   Get currently configured PCI ASPM policy to name.

**--policies** *NAME*
   Get list of available PCI ASPM policy to names.

**--device** *ADDR*
   PCI device address for the '--l1-aspm' option. Example: '0000:00:02.0'.

**--l1-aspm**
   Enable or disable L1 ASPM for the PCI device specified with --device option. Make sure the kernel
   version is at least 5.5 and is compiled with CONFIG_PCIEASPM and CONFIG_PCIEASPM_DEFAULT for this
   option to work.

Subcommand *'config'*
=====================

Change PCI ASPM configuration.

**--policy** *NAME*
   The PCI ASPM policy to set, use "default" to set the default policy.

**--device** *ADDR*
   PCI device address for the '--l1-aspm' option. Example '0000:00:02.0'.

**--l1-aspm** *OPTION*
   Enable or disable L1 ASPM for a particular device. Valid arguments are 'on', 'off',
   'enable', 'disable', 'true', 'false'. The argument is case insensitive. Make sure the kernel
   version is at least 5.5 and is compiled with CONFIG_PCIEASPM and CONFIG_PCIEASPM_DEFAULT for this
   option to work.
