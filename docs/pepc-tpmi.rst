.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Date:   09-02-2024
:Title:  ASPM

.. Contents::
   :depth: 2
..

================
Command *'tpmi'*
================

Background
==========

TPMI stands for Topology Aware Register and PM Capsule Interface and it is a memory-mapped interface
for reading and writing processor's registers related to power management features on Intel CPUs.

TPMI registers are exposed by the processor via PCIe VSEC (Vendor-Specific Extended Capabilities),
and the registers are grouped into TPMI features. For example, the "uncore" TPMI feature includes
processor registers related to uncore frequency scaling. The "rapl" TPMI feature includes processor
registers related to processor's Running Average Power Limit (RAPL). The "sst" feature includes
processor registers related to Intel Speed Select Technology (SST).

In order for the 'pepc' tool to decode TPMI features, the spec file is required. The spec file
describes the register names, bits, and offsets in the memory-mapped PCIe address space. If there
is no spec file for a feature, it cannot be decoded.

The 'pepc' project comes with some standard pepc files, which will be searched for in the following
locations and in the following order.

   1. './tpmi', in the directory of the running program
   2. '$PEPC_DATA_PATH/tpmi'
   3. '$HOME/.local/share/pepc/tpmi'
   4. '/usr/local/share/pepc/tpmi'
   5. '/usr/share/pepc/tpmi'

In addition to this, users can provide custom/private spec files by placing them to a directory
and specifying the directory path via the 'PEPC_TPMI_DATA_PATH' environment variable.

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

Subcommand *'ls'*
=================

List supported TPMI features.

**--all**
   Also print IDs of TPMI features supported by the processor, but for which there are no spec files,
   so they cannot be decoded.
