.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: Topology

.. contents::
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

Subcommand *'info'*
===================

Display CPU topology details.

**Note 1**: The Linux kernel provides topology data only for online CPUs. For offline CPUs, unknown
topology values (e.g., package number) are replaced with "?".

**Note 2**: In case of non-compute dies (dies without any CPUs, for example I/O dies on Granite
Rapids Xeon), CPU, core, and module numbers are shown as "-".

**--cpus** *CPUS*
   The list can include individual CPU numbers and CPU number ranges. For example, '1-4,7,8,10-12'
   would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the special keyword 'all' to specify all
   CPUs.

**--cores** *CORES*
   The list can include individual core numbers and core number ranges. For example, '1-4,7,8,10-12'
   would mean cores 1 to 4, cores 7, 8, and 10 to 12. Use the special keyword 'all' to specify all
   cores. This option has to be used with the '--packages' option, because core numbers are
   relative to the package.

**--modules** *MODULES*
   The list can include individual module numbers and module number ranges. For example, '0,2-5'
   would mean module 0 and modules 2, 3, 4, and 5. Use the special keyword 'all' to specify all
   modules. Note, unlike core and die numbers, module numbers are absolute.

**--dies** *DIES*
   The list can include individual die numbers and die number ranges. For example, '0-3,5' would
   mean dies 0 to 3, and die 5. Use the special keyword 'all' to specify all dies. On some systems,
   die numbers are globally unique, while on other systems they are relative to the package. In the
   latter case, this option has to be used with the '--packages' option.

**--packages** *PACKAGES*
   The list can include individual package numbers and package number ranges. For example, '0,2-4'
   would mean package 0 and packages 2 to 4. Use the special keyword 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   Core siblings are CPUs sharing the same core. The list can include individual core sibling
   indices or index ranges. For example, if a core includes CPUs 2 and 3, index 0 would mean CPU 2
   and index 1 would mean CPU 3. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the example with CPUs 2 and 3,
   if CPU 2 was offline, then index 0 would mean CPU 3. On Intel processors with hyper-threading,
   this is typically used to offline hyperthreads.

**--module-siblings** *MODULE_SIBLINGS*
   Module siblings are CPUs sharing the same module. The list can include individual module sibling
   indices or index ranges. For example, if a module includes CPUs 4, 5, 6, and 7, index 0 would
   mean CPU 4, index 1 would mean CPU 5, index 2 would mean CPU 6, and index 3 would mean CPU 7.
   This option can only be used to reference online CPUs, because Linux does not provide topology
   information for offline CPUs. In the example with CPUs 4, 5, 6, and 7, if CPU 5 was offline,
   then index 1 would mean CPU 6, index 2 would mean CPU 7, and index 3 would be invalid.

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
