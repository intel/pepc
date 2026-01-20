.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: TPMI

.. contents::
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
TPMI features. For instance, the "ufs" feature includes registers for uncore frequency scaling,
the "rapl" feature covers Running Average Power Limit (RAPL) registers, and the "sst" feature
includes registers for Intel Speed Select Technology (SST).

To decode TPMI features, the 'pepc' tool requires a spec file describing register names, bits, and
offsets in the PCIe memory-mapped address space. Features without a spec file cannot be decoded.

The 'pepc' project includes spec files for some, but not all TPMI features. Spec files for other
features can be requested from Intel Corporation via customer support channels.

The spec files are searched in the following locations and order:

   1. './tpmi', in the directory of the running program
   2. '$PEPC_TPMI_DATA_PATH/tpmi'
   3. '$HOME/.local/share/pepc/tpmi'
   4. '$VIRTUAL_ENV/share/pepc/tpmi'
   5. '/usr/local/share/pepc/tpmi'
   6. '/usr/share/pepc/tpmi'

The 'PEPC_TPMI_DATA_PATH' provides a mechanism for replacing or extending the standard spec files. Just
set it to a directory with spec files to have 'pepc' use them.

Spec files are YAML files, but they are generated from Intel proprietary XML files using the
'tpmi-spec-files-generator' tool available in the 'pepc' source code repository.

General options
===============

**-h**
   Show a short help message and exit.

**-q**
   Be quiet (print only important messages like warnings).

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
   Name of the user to use for logging into the remote host over SSH. The default user name is
   'root'.

**-K** *PRIVKEY*, **--priv-key** *PRIVKEY*
   Path to the private SSH key for logging into the remote host. Defaults to keys in standard paths
   like '$HOME/.ssh'.

**-T** *TIMEOUT*, **--timeout** *TIMEOUT*
   Timeout for establishing an SSH connection in seconds. Defaults to 8.

**-D** *DATASET*, **--dataset** *DATASET*
   This option is for debugging and testing. It specifies the dataset to use for emulating the host
   for running the command on. The datasets are available in 'pepc' source code repository.

   The argument can be a dataset path or name. If specified by name, the following locations are
   searched for the dataset.

   1. './tests/emul-data' in the program's directory
   2. '$PEPC_DATA_PATH/tests/emul-data'
   3. '$HOME/.local/share/pepc/tests/emul-data'
   4. '$VIRTUAL_ENV/share/tests/emul-data'
   5. '/usr/local/share/pepc/tests/emul-data'
   6. '/usr/share/pepc/tests/emul-data'

**--force-color**
   Force colorized output even if the output stream is not a terminal (adds ANSI escape codes).

**--print-man-path**
   Print path to pepc manual pages directory and exit. This path can be added to the 'MANPATH'
   environment variable to make the manual pages available to the 'man' tool.

Subcommand *'ls'*
=================

Display supported TPMI features.

**-t**, **--topology**
   Display TPMI topology (PCI addresses, instance numbers, etc.).

**-F** *[FEATURES]*, **--features** *[FEATURES]*
   Comma-separated list of TPMI feature names to include in the output. Defaults to all supported
   features.

**--unknown**
   Include TPMI features without spec files (unknown features).

Subcommand *'read'*
===================

Read one or more TPMI registers.

**-F** *[FEATURES]*, **--features** *[FEATURES]*
   Comma-separated list of TPMI feature names to read the registers for. Defaults to all supported
   features.

**-a** *[ADDRS]*, **--addresses** *[ADDRS]*
   Comma-separated list of TPMI device PCI addresses to read the registers from. Defaults to all
   devices.

**--packages** *[PACKAGES]*
   Comma-separated list of package numbers to read TPMI registers for (defaults to all packages).

**-i** *[INSTANCES]*, **--instances** *[INSTANCES]*
   Comma-separated list of TPMI instance numbers to read registers from (defaults to all instances).

**-c** *[CLUSTERS]*, **--clusters** *[CLUSTERS]*
   Comma-separated list of cluster numbers to read registers (defaults to all clusters). This option
   is only useful for the 'ufs' TPMI feature, because there may be multiple copies of UFS control
   registers within a TPMI instance, and the copies are referred to as clusters. All other TPMI
   features have only one cluster - cluster 0.

**-R** *[REGISTERS]*, **--registers** *[REGISTERS]*
   Comma-separated list of TPMI register names to read. Defaults to all registers.

**-b** *[BFNAMES]*, **--bitfields** *[BFNAMES]*
   Comma-separated list of TPMI register bit field names to read. Defaults to all bit fields.

**-n**, **--no-bitfields**
   Do not decode and display TPMI register bit fields, only display register values.

**--yaml**
   Output information in YAML format.

Subcommand *'write'*
====================

Write a value to a TPMI register or its bit field.

**-F** *FEATURE*, **--feature** *FEATURE*
   Name of the TPMI feature the register belongs to.

**-a** *ADDRS*, **--addresses** *ADDRS*
   Comma-separated list of PCI addresses of TPMI devices to write to.

**--packages** *PACKAGES*
   Comma-separated list of package numbers to write to (defaults to all packages).

**-i** *INSTANCES*, **--instances** *INSTANCES*
   Comma-separated list of TPMI instance numbers to write to. Defaults to all instances.

**-R** *REGNAME*, **--register** *REGNAME*
   Name of the TPMI register to write.

**-b** *BITFIELD*, **--bitfield** *BITFIELD*
   Name of the TPMI register bitfield to write. Defaults to writing to the entire register if not
   specified.

**-V** *VALUE*, **--value** *VALUE*
   Value to write to the TPMI register or bit field.
