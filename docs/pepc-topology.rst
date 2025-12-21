.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: Topology

.. Contents::
   :depth: 2
..

====================
Command *'topology'*
====================

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

Subcommand *'info'*
===================

Display CPU topology details.

**Note**: The Linux kernel provides topology data only for online CPUs. For offline CPUs, unknown
topology values (e.g., package number) are replaced with "?".

**--cpus** *CPUS*
   Specify CPUs to display topology information for. Accepts individual CPU numbers or ranges,
   e.g., '1-4,7,8,10-12' for CPUs 1 to 4, 7, 8, and 10 to 12. Use 'all' to include all CPUs.

**--cores** *CORES*
   Specify cores to display topology information for. Accepts individual core numbers or ranges,
   e.g., '1-4,7,8,10-12' for cores 1 to 4, 7, 8, and 10 to 12. Use 'all' to include all cores. This
   option requires the '--package' option, as core numbers are relative to the package.

**--modules** *MODULES*
   Specify modules to display topology information for. Accepts individual module numbers or ranges,
   e.g., '0,2-5' for modules 0, 2, 3, 4, and 5. Use 'all' to include all modules.

**--dies** *DIES*
   Specify dies to display topology information for. Accepts individual die numbers or ranges,
   e.g., '0-3,5' for dies 0 to 3 and die 5. Use 'all' to include all dies. On some systems, die
   numbers are globally unique, while on others they are relative to the package. In the latter
   case, this option requires the '--package' option.

**--packages** *PACKAGES*
   Specify packages to display topology information for. Accepts individual package numbers or
   ranges, e.g., '0,2-4' for package 0 and packages 2 to 4. Use 'all' to include all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices (CPUs sharing the same core). Specify individual indices or ranges.
   For example, if a core includes CPUs 2 and 3, index '0' refers to CPU 2, and index '1' refers to
   CPU 3. This option applies only to online CPUs, as Linux lacks topology details for offline CPUs.
   If CPU 2 is offline, index '0' refers to CPU 3. On Intel processors with hyper-threading, this is
   typically used to offline hyperthreads.

**--module-siblings** *MODULE_SIBLINGS*
   List of module sibling indices (CPUs sharing the same module). Specify individual indices or
   ranges. For example, if a module includes CPUs 4, 5, 6, and 7, index '0' refers to CPU 4, index
   '1' to CPU 5, and index '4' to CPU 7. This option applies only to online CPUs, as Linux lacks
   topology details for offline CPUs. In the example, if CPU 5 is offline, index '1' refers to
   CPU 1.

**--order** *ORDER*
   By default, the topology table is sorted by CPU number. Use this option to sort by core, module,
   die, node, or package number instead. Supported values: cpu, core, module, die, node, package.

**--online-only**
   Include only online CPUs. By default, both online and offline CPUs are included.

**--columns** *COLUMNS*
   Comma-separated list of topology columns to display. Available columns: CPU, core, module, die,
   node, package, hybrid. Example: --columns Package,Core,CPU. By default, all relevant columns for
   the platform are shown. Columns like "module" or "die" are omitted if not applicable. The "hybrid"
   column is shown only for hybrid platforms.
