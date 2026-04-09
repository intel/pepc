.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: PM QoS

.. contents::
   :depth: 2
..

===================
Command *'pmqos'*
===================

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

Target CPU specification options
================================

All subcommands (*'info'*, *'config'*) accept the following target CPU specification
options.

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
   indices or index ranges. For example, if a core includes CPUs 3 and 4, index 0 would mean
   CPU 3 and index 1 would mean CPU 4. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the example with CPUs 3 and 4,
   if CPU 3 was offline, then index 0 would mean CPU 4 and index 1 would be invalid.

**--module-siblings** *MODULE_SIBLINGS*
   Module siblings are CPUs sharing the same module. The list can include individual module sibling
   indices or index ranges. For example, if a module includes CPUs 3, 4, 5, and 6, index 0 would
   mean CPU 3, index 1 would mean CPU 4, index 2 would mean CPU 5, and index 3 would mean
   CPU 6. This option can only be used to reference online CPUs, because Linux does not provide
   topology information for offline CPUs. In the example with CPUs 3, 4, 5, and 6, if CPU 4 was
   offline, then index 1 would mean CPU 5, index 2 would mean CPU 6, and index 3 would be invalid.

Subcommand *'info'*
===================

Retrieve PM QoS (Power Management Quality of Service) information for specified CPUs. By default,
display all details for all CPUs. Use target CPU specification options to define a subset of CPUs,
cores, dies, or packages.

**--latency-limit**
   Retrieve the per-CPU Linux PM QoS limit. This limit affects C-state selection by restricting the
   kernel from using C-states with latencies exceeding the specified limit. For example, a 50us
   limit ensures the kernel only selects C-states with latencies ≤ 50us. The limit is read from
   '/sys/devices/system/cpu/cpu<NUMBER>/power/pm_qos_resume_latency_us'.

**--global-latency-limit**
   Retrieve the global Linux PM QoS limit. This limit, unlike the per-CPU latency limit, applies
   globally. It is read from the '/dev/cpu_dma_latency' device node.

**--yaml**
   Display information in YAML format.

Subcommand *'config'*
=====================

Configure PM QoS (Power Management Quality of Service) for specified CPUs. If no parameter is
provided, the current value(s) will be displayed. Use target CPU specification options to define
the subset of CPUs, cores, dies, or packages.

**--latency-limit** *[LIMIT]*
   Set the per-CPU Linux PM QoS limit, which restricts the kernel from using C-states with latencies
   exceeding the specified value. For example, a 50us limit ensures the kernel selects only C-states
   with latencies ≤ 50us. The limit is configured via
   '/sys/devices/system/cpu/cpu<NUMBER>/power/pm_qos_resume_latency_us'. The default unit is 'us'
   (microseconds), but 'ns', 'ms', and 's' units are also supported (e.g., '1ms'). Value 0 disables
   the limit.

Note: Setting the global latency limit is unsupported because the '/dev/cpu_dma_latency' API
requires the setter to keep the device open for the limit to remain effective. The limit is
removed as soon as the device is closed.
