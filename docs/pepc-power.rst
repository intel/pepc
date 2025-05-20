.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Date:   02-05-2023
:Title:  POWER

.. Contents::
   :depth: 2
..

===================
Command *'power'*
===================

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

**--override-cpu-model** *VFM*
   This option is for debugging and testing purposes only. Override the target host CPU model and
   force {TOOLNAME} treat the host as a specific CPU model. The format is
   '[<Vendor>:][<Family>:]<Model>', where '<Vendor>' is the CPU vendor (e.g., 'GenuineIntel' or
   'AuthenticAMD'), '<Family>' is the CPU family (e.g., 6), and '<Model>' is the CPU model (e.g.,
   0x8F). Example: 'GenuineIntel:6:0x8F' will force the tool treating the target host CPU as a
   Sapphire Rapids Xeon. The vendor and family are optional and if not specified, the tool will use
   the vendor and family of the target host CPU. The family and model can be specified in decimal
   or hexadecimal format.

Target CPU specification options
================================

All sub-commans (*'info'*, *'config'*) support the following target CPU specification options.

**--cpus** *CPUS*
   The list can include individual CPU numbers and CPU number ranges. For example,'1-4,7,8,10-12'
   would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the special keyword 'all' to specify all
   CPUs.

**--cores** *CORES*
   The list can include individual core numbers and core number ranges. For example, '1-4,7,8,10-12'
   would mean cores 1 to 4, cores 7, 8, and 10 to 1. Use the special keyword 'all' to specify all
   cores. This option has to be accompanied by the '--package' option, because core numbers are
   per-package.

**--modules** *MODULES*
   The list can include individual module numbers and module number ranges. For example, '0,2-5'
   would mean module 0 and modules 2, 3, 4, and 5. Use the special keyword 'all' to specify all
   modules. Note, unlike core and die numbers, module numbers are absolute.

**--dies** *DIES*
   The list can include individual die numbers and die number ranges. For example, '0-3,5' would
   mean dies 0 to 3, and die 5. Use the special keyword 'all' to specify all dies. On some systems,
   die numbers are globally unique, while on other systems they are relative to the package. In the
   latter case, this option has to be accompanied by the '--package' option.

**--packages** *PACKAGES*
   The list can include individual package numbers and package number ranges. For example, '0,2-4'
   would mean package 0 and packages 2 to 4. Use the special keyword 'all' to specify all packages.

Subcommand *'info'*
===================

Retrieve power-related information for specified CPUs. By default, displays all details for all CPUs.

Use target CPU specification options to define the subset of CPUs, cores, dies, or packages.

**--yaml**
   Display information in YAML format.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   Comma-separated list of mechanisms for retrieving power information. Currently, only the 'msr'
   mechanism is supported.

**--list-mechanisms**
   List available mechanisms for retrieving power information.

**--tdp**
   Retrieve the CPU package thermal design power (TDP) in Watts from MSR_PKG_POWER_INFO (**0x614**),
   bits **14:0**.

**--ppl1**
   Retrieve RAPL package power limit #1 in Watts from MSR_PKG_POWER_LIMIT (**0x610**), bits **14:0**.

**--ppl1-enable**
   Check if RAPL package power limit #1 is enabled via MSR_PKG_POWER_LIMIT (**0x610**, bit **15**)
   and display the result.

**--ppl1-clamp**
   Check if RAPL package power limit #1 clamping is enabled via MSR_PKG_POWER_LIMIT (**0x610**, bit
   **16**) and display the result.

**--ppl1-window**
   Retrieve the RAPL package power limit #1 window size in seconds from MSR_PKG_POWER_LIMIT
   (**0x610**), bits **23:17**.

**--ppl2**
   Retrieve RAPL package power limit #2 in Watts from MSR_PKG_POWER_LIMIT (**0x610**), bits
   **46:32**.

**--ppl2-enable**
   Check if RAPL package power limit #2 is enabled via MSR_PKG_POWER_LIMIT (**0x610**, bit **47**)
   and display the result.

**--ppl2-clamp**
   Get RAPL package power limit #2 clamping enable status via MSR_PKG_POWER_LIMIT (**0x610**, bit
   **48**) and display the result.

**--ppl2-window**
   Retrieve the RAPL package power limit #2 window size in seconds from MSR_PKG_POWER_LIMIT
   (**0x610**), bit **55:49**.

Subcommand *'config'*
=====================

Configure power for specified CPUs. If no parameter is provided, the current value(s) will be
displayed.

Use target CPU specification options to define the subset of CPUs, cores, dies, or packages.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   Comma-separated list of mechanisms for configuring power. Currently, only the 'msr' mechanism
   is supported.

**--list-mechanisms**
   List available mechanisms for configuring power.

**--ppl1** *PPL1*
   Configure RAPL package power limit #1 in Watts using MSR_PKG_POWER_LIMIT (**0x610**), bits
   **14:0**.

**--ppl1-enable** *on|off*
   Toggle RAPL package power limit #1 using MSR_PKG_POWER_LIMIT (**0x610**, bit **15**).

**--ppl1-clamp** *on|off*
   Toggle RAPL package power limit #1 clamping using MSR_PKG_POWER_LIMIT (**0x610**, bit **16**).

**--ppl2** *PPL2*
   Configure RAPL package power limit #2 in Watts using MSR_PKG_POWER_LIMIT (**0x610**), bits
   **46:32**.

**--ppl2-enable** *on|off*
   Toggle RAPL package power limit #2 using MSR_PKG_POWER_LIMIT (**0x610**, bit **47**).

**--ppl2-clamp** *on|off*
   Toggle RAPL package power limit #2 clamping using MSR_PKG_POWER_LIMIT (**0x610**, bit
   **48**).
