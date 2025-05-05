.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: TPMI

.. Contents::
   :depth: 2
..

================
Command *'tpmi'*
================

Background
==========

TPMI, or Topology Aware Register and PM Capsule Interface, is a memory-mapped interface for
accessing processor registers related to power management on Intel CPUs.

These registers are exposed via PCIe VSEC (Vendor-Specific Extended Capabilities) and grouped into
TPMI features. For instance, the "uncore" feature includes registers for uncore frequency scaling,
the "rapl" feature covers Running Average Power Limit (RAPL) registers, and the "sst" feature
includes registers for Intel Speed Select Technology (SST).

To decode TPMI features, the 'pepc' tool requires a spec file describing register names, bits, and
offsets in the PCIe memory-mapped address space. Features without a spec file cannot be decoded.

The 'pepc' project includes standard spec files searched in the following locations and order:

   1. './tpmi', in the directory of the running program
   2. '$PEPC_DATA_PATH/tpmi'
   3. '$HOME/.local/share/pepc/tpmi'
   4. '$VIRTUAL_ENV/share/pepc/tpmi'
   5. '/usr/local/share/pepc/tpmi'
   6. '/usr/share/pepc/tpmi'

Users can also provide custom spec files by placing them in a directory and setting its path via the
'PEPC_TPMI_DATA_PATH' environment variable. Standard spec files are based on public documentation
available at https://github.com/intel/tpmi_power_management/.

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
   User name for SSH login to the remote host. Defaults to 'root.

**-U** *USERNAME*, **--username** *USERNAME*
   Name of the user to use for logging into the remote host over SSH. The default user name is
   'root'.

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

Subcommand *'ls'*
=================

Display supported TPMI features.

**-l**, **--long**
   Include details like TPMI device PCI addresses and instance numbers for more specific output.

**--all**
   Include IDs of TPMI features supported by the processor but lacking spec files for decoding.

Subcommand *'read'*
===================

Read one or more TPMI registers.

**-F** FEATURES, **--features** FEATURES
   Comma-separated list of TPMI feature names to read the registers for. Defaults to all supported
   features.

**-a** ADDRS, **--addresses** ADDRS
   Comma-separated list of TPMI device PCI addresses to read the registers from. Defaults to all
   devices.

**--packages** PACKAGES
   Comma-separated list of package numbers to read TPMI registers for (defaults to all packages).

**-i** INSTANCES, **--instances** INSTANCES
   Comma-separated list of TPMI instance numbers to read registers from (defaults to all instances).

**-R** REGISTERS, **--registers** REGISTERS
   Comma-separated list of TPMI register names to read. Defaults to all registers.

**-b** BFNAMES, **--bitfields** BFNAMES
   Comma-separated list of TPMI register bit field names to read. Defaults to all bit fields.

**--yaml**
   Output information in YAML format.

Subcommand *'write'*
====================

Write a value to a TPMI register or its bit field.

**-F** FEATURE, **--feature** FEATURE
   Name of the TPMI feature the register belongs to.

**-a** ADDRS, **--addresses** ADDRS
   Comma-separated list of PCI addresses of TPMI devices to write to.

**--packages** PACKAGES
   Comma-separated list of package numbers to write to (defaults to all packages).

**-i** INSTANCES, **--instances** INSTANCES
   Comma-separated list of TPMI instance numbers to write to. Defaults to all instances.

**-R** REGNAME, **--register** REGNAME
   Name of the TPMI register to write.

**-b** BITFIELD, **--bitfield** BITFIELD
   Name of the TPMI register bitfield to write. Defaults to writing to the entire register if not
   specified.

**-V** VALUE, **--value** VALUE
   Value to write to the TPMI register or bit field.
