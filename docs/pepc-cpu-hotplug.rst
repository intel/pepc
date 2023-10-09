.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Date:   09-03-2023
:Title:  CPU-HOTPLUG

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

List all online and offline CPUs.

Subcommand *'online'*
=====================

Bring CPUs online.

**--cpus** *CPUS*
   List of CPUs to online. The list can include individual CPU numbers and CPU number ranges.
   For example,'1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the special
   keyword 'all' to specify all CPUs.

Subcommand *'offline'*
======================

Bring CPUs offline.

**--cpus** *CPUS*
   List of CPUs to offline. The list can include individual CPU numbers and CPU number ranges.
   For example,'1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the special
   keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to offline. The list can include individual core numbers and core number ranges.
   For example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12. Use the special
   keyword 'all' to specify all cores. This option has to be accompanied by '--package' option,
   because core numbers are per-package.

**--packages** *PACKAGES*
   List of packages to offline. The list can include individual package numbers and package number
   ranges. For example, '0,2-4' would mean package 0 and packages 2 to 4. Use the special keyword
   'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to offline. The list can include individual core sibling indices or
   index ranges. For example, core x includes CPUs 3 and 4, '0' would mean CPU 3 and '1' would mean
   CPU 4. This option can only be used to reference online CPUs, because Linux does not provide
   topology information for offline CPUs. In the previous example if CPU 3 was offline, then '0'
   would mean CPU 4.
