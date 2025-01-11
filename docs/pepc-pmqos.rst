.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: PM QoS

.. Contents::
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

Target CPU specification options
================================

All sub-commans (*'info'*, *'config'*, *'save'*) support the following target CPU specification
options.

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

**--core-siblings** *CORE_SIBLINGS*
   Core siblings are CPUs sharing the same core. The list can include individual core sibling
   indices or index ranges. For example, if a core includes CPUs 3 and 4, index '0' would mean CPU 3
   and index '1' would mean CPU 4. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the example with CPUs 3 and 4,
   if CPU 3 was offline, then index '0' would mean CPU 4.

**--module-siblings** *MODULE_SIBLINGS*
   Module siblings are CPUs sharing the same module. The list can include individual module sibling
   indices or index ranges. For example, if a module includes CPUs 3, 4, 5, and 6, index '0' would
   mean CPU 3, index '1' would mean CPU 4, and idex '3' would mean CPU 5. This option can only be
   used to reference online CPUs, because Linux does not provide topology information for offline
   CPUs. In the example with CPUs 3, 4, 5 and 6, if CPU 4 was offline, then index '1' would mean
   CPU 5.

Subcommand *'info'*
===================

Get PM QoS (Power Management Quality of Service) information for specified CPUs. By default, print
all information about all CPUs.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**--yaml**
   Print information in YAML format.

**--override-cpu-model** *MODEL*
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**--list-mechanisms**
   List mechanisms available for reading PM QoS information.

**--latency-limit**
   Get the per-CPU Linux PM QoS limit (details in 'latency_limit_').

**--global-latency-limit**
   Get the global Linux PM QoS limit (details in 'global_latency_limit_').

Subcommand *'config'*
=====================

Configure PM QoS (Power Management Quality of Service) on specified CPUs. All options can be used
without a parameter, in which case the currently configured value(s) will be printed.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**--override-cpu-model** *MODEL*
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
    Comma-separated list of mechanisms that are allowed to be used for configuring PM QoS. Use
    '--list-mechanisms' to get the list of available mechanisms. Note, many options support only one
    mechanism (e.g., 'sysfs'), some may support multiple (e.g., 'sysfs' and 'msr'). The mechanisms
    are tried in the specified order. By default, all mechanisms are allowed and the most
    preferred mechanisms will be tried first.

**--list-mechanisms**
   List mechanisms available for configuring PM QoS.

**--latency-limit** *LIMIT*
   Set the per-CPU Linux PM QoS limit (details in 'latency_limit_').

Subcommand *'save'*
===================

Save all the modifiable PM QoS (Power Management Quality of Service) settings into a file. This file
can later be used for restoring PM QoS settings with the 'pepc pmqos restore' command.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**-o** *OUTFILE*, **--outfile** *OUTFILE*
   Name of the file to save the settings to (print to standard output by default).

Subcommand *'restore'*
======================

Restore PM QoS (Power Management Quality of Service)e settings from a file previously created with
the 'pepc pmqos save' command.

**-f** *INFILE*, **--from** *INFILE*
   Name of the file from which to restore the settings from, use "-" to read from the standard
   output.

----------------------------------------------------------------------------------------------------

==========
Properties
==========

latency_limit
=============

latency_limit - per-CPU Linux PM QoS limit

Synopsis
--------

| pepc pmqos *info* **--latency-limit**
| pepc pmqos *config* **--latency-limit**\ =<value>

Description
-----------

Get or set Linux per-CPU PM QoS limit via the sysfs interface.

Linux kernel includes the Power Management Quality of Service (PM QoS) subsystem, which allows
user-space programs to specify latency limits. These limits influence various aspects of system
performance, including C-state selection: the Linux kernel will avoid using C-states with latencies
greater than the strictest specified limit. For example, if user sets a 50us latency limit for
CPU0, the Linux idle governors will only request C-states with latency of less or equivalent to
50us. For more information, please refer Linux kernel PM QoS documentation.

The default unit is 'us' (microseconds), but 'ns', 'us', 'ms' and 's' units can also be used
(for example "1ms").

Value 0 is special, and it means "no latency limit".

Mechanisms
----------

**sysfs**
"/sys/devices/system/cpu/cpu0/power/pm_qos_resume_latency_us", where '0' is replaced with desired
CPU number.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

global_latency_limit
====================

global_latency_limit - global Linux PM QoS limit

Synopsis
--------

| pepc pmqos *info* **--global-latency-limit**

Description
-----------

Get Linux global PM QoS limit via the '/dev/cpu_dma_latency' device node.

Linux kernel includes the Power Management Quality of Service (PM QoS) subsystem, which allows
user-space programs to specify latency limits. These limits influence various aspects of system
performance, including C-state selection: the Linux kernel will avoid using C-states with latencies
greater than the strictest specified limit. For example, if a process sets a 50us global latency
limit, the Linux idle governors will only request C-states with latency of less or equivalent to
50us. For more information, please refer Linux kernel PM QoS documentation.

The default unit is 'us' (microseconds), but 'ns', 'us', 'ms' and 's' units can also be used
(for example "1ms").

Value 0 is means the minimum latency, Linux will only request the POLL state in this case.

Mechanisms
----------

**cdev**
The "/dev/cpu_dma_latency" character device node.

Scope
-----

This property has global scope.