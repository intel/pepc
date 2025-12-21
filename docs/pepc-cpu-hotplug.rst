.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title:  CPU-hotplug

.. Contents::
   :depth: 2
..

=======================
Command *'cpu-hotplug'*
=======================

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

Display the list of online and offline CPUs.

Subcommand *'online'*
=====================

Bring specified CPUs online.

**--cpus** *CPUS*
   List of CPUs to bring online. Specify individual CPU numbers or ranges, e.g., '1-4,7,8,10-12'
   for CPUs 1 to 4, 7, 8, and 10 to 12. Use 'all' to specify all CPUs.

Subcommand *'offline'*
======================

Bring specified CPUs offline.

**--cpus** *CPUS*
   List of CPUs to bring offline. Specify individual CPU numbers or ranges, e.g., '1-4,7,8,10-12'
   for CPUs 1 to 4, 7, 8, and 10 to 12. Use 'all' to specify all CPUs.

**--cores** *CORES*
   LIst of cores to bring offline using individual core numbers or ranges, e.g., '1-4,7,9-11' for
   cores 1 to 4, 7, and 9 to 11. Use 'all' to specify all cores. This option requires the
   '--package' option, as core numbers are package-specific.

**--modules** *MODULES*
   List of modules to offline, specified as individual module numbers or ranges (e.g., '0,2-5' for
   module 0 and modules 2 to 5). Use 'all' to specify all modules. Unlike core and die numbers,
   module numbers are absolute.

**--dies** *DIES*
   List dies to bring offline using, specified as individual die numbers or ranges, e.g., '0-3,5'
   for dies 0 to 3 and 5.  Use 'all' to specify all dies. On some systems, die numbers are globally
   unique, while on others they are relative to the package. In the latter case, the '--package'
   option must be specified.

**--packages** *PACKAGES*
   List of packages to bring offline, specified as individual package numbers or ranges (e.g.,
   '0,2-4' for package 0 and packages 2 to 4). Use 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices (CPUs sharing the same core) to bring offline. Specify individual
   indices or ranges. For example, if a core includes CPUs 2 and 3, index '0' refers to CPU 2, and
   index '1' refers to CPU 3. This option applies only to online CPUs, as Linux lacks topology
   details for offline CPUs. If CPU 2 is offline, index '0' refers to CPU 3. On Intel processors
   with hyper-threading, this is typically used to offline hyperthreads.

**--module-siblings** *MODULE_SIBLINGS*
   List of module sibling indices (CPUs sharing the same module) to bring offline. Specify individual
   indices or ranges. For example, if a module includes CPUs 4, 5, 6, and 7, index '0' refers to CPU 4,
   index '1' to CPU 5, and index '4' to CPU 7. This option applies only to online CPUs, as Linux lacks
   topology details for offline CPUs. In the example, if CPU 5 is offline, index '1' refers to CPU 6.
