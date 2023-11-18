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
   cores. This option has to be accompanied by '--package' option, because core numbers are
   per-package.

**--modules** *MODULES*
   The list can include individual module numbers and module number ranges. For example, '0,2-5'
   would mean module 0 and modules 2, 3, 4, and 5. Use the special keyword 'all' to specify all
   modules. Note, unlike core and die numbers, module numbers are absolute.

**--dies** *DIES*
   The list can include individual die numbers and die number ranges. For example, '0-3,5' would
   mean dies 0 to 3, and die 5. Use the special keyword 'all' to specify all dies. This option has
   to be accompanied by '--package' option, because die numbers are per-package.

**--packages** *PACKAGES*
   The list can include individual package numbers and package number ranges. For example, '0,2-4'
   would mean package 0 and packages 2 to 4. Use the
   special keyword 'all' to specify all packages.

Subcommand *'info'*
===================

Get information about power on specified CPUs. By default, prints all information for all CPUs.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**--yaml**
   Print information in YAML format.

**--override-cpu-model** *MODEL*
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
    Comma-separated list of mechanisms that are allowed to be used for configuring power. Use
    '--list-mechanisms' to get the list of available mechanisms. Note, many options support only one
    mechanism (e.g., 'sysfs'), some may support multiple (e.g., 'sysfs' and 'msr'). The mechanisms
    are tried in the specified order. By default, all mechanisms are allowed and the most
    preferred mechanisms will be tried first.

**--list-mechanisms**
   List mechanisms available for reading power information.

**--tdp**
   Get CPU package thermal design power (details in 'tdp_')

**--ppl1**
   Get RAPL package power limit #1 value via MSR (details in 'ppl1_').

**--ppl1-enable**
   Get RAPL package power limit #1 enable status via MSR (details in 'ppl1_enable_').

**--ppl1-clamp**
   Get RAPL package power limit #1 clamping enable status via MSR (details in 'ppl1_clamp_')

**--ppl1-window**
   Get RAPL package power limit #1 window size via MSR (details in 'ppl1_window_').

**--ppl2**
   Get RAPL package power limit #2 value via MSR (details in 'ppl2_').

**--ppl2-enable**
   Get RAPL package power limit #2 enable status via MSR (details in 'ppl2_enable_').

**--ppl2-clamp**
   Get RAPL package power limit #2 clamping enable status via MSR (details in 'ppl2_clamp_')

**--ppl2-window**
   Get RAPL package power limit #2 window size via MSR (details in 'ppl2_window_').

Subcommand *'config'*
=====================

Configure power on specified CPUs. All options can be used without a parameter, in which case the
currently configured value(s) will be printed.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**--override-cpu-model** *MODEL*
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**--list-mechanisms**
   List mechanisms available for configuring power.

**--ppl1** *PPL1*
   Set RAPL package power limit #1 value via MSR (details in 'ppl1_').

**--ppl1-enable** *on|off*
   Enable or disable RAPL package power limit #1 via MSR (details in 'ppl1_enable_').

**--ppl1-clamp** *on|off*
   Enable or disable RAPL package power limit #1 clamping via MSR (details in 'ppl1_clamp_')

**--ppl2** *PPL2*
   Set RAPL package power limit #2 value via MSR (details in 'ppl2_').

**--ppl2-enable** *on|off*
   Enable or disable RAPL package power limit #2 via MSR (details in 'ppl2_enable_').

**--ppl2-clamp** *on|off*
   Enable or disable RAPL package power limit #2 clamping via MSR (details in 'ppl2_clamp_')

Subcommand *'save'*
===================

Save all the modifiable power settings into a file. This file can later be used for restoring
power settings with the 'pepc power restore' command.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**-o** *OUTFILE*, **--outfile** *OUTFILE*
   Name of the file to save the settings to.

Subcommand *'restore'*
======================

Restore power settings from a file previously created with the 'pepc power save' command.

**-f** *INFILE*, **--from** *INFILE*
   Name of the file from which to restore the settings from, use "-" to read from the standard
   output.

----------------------------------------------------------------------------------------------------

==========
Properties
==========

tdp
===

tdp - CPU package thermal design power

Synopsis
--------

| pepc power *info* [**--tdp**]

Description
-----------

CPU package thermal design power in Watts.

Mechanism
---------

MSR_PKG_POWER_INFO (**0x614**), bits **14:0**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

ppl1
====

ppl1 - RAPL package power limit #1 value in Watts

Synopsis
--------

| pepc power *info* **--ppl1**
| pepc power *config* **--ppl1**\ =<value>

Description
-----------

Average power usage limit of the package domain corresponding to time window #1.

Mechanism
---------

MSR_PKG_POWER_LIMIT (**0x610**), bits **14:0**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

ppl1_enable
===========

ppl1_enable - Enable or disable RAPL package power limit #1

Synopsis
--------

| pepc power *info* **--ppl1-enable**
| pepc power *config* **--ppl1-enable**\ =<on|off>

Description
-----------

Enable or disable RAPL package power limit #1.

Mechanism
---------

MSR_PKG_POWER_LIMIT (**0x610**), bit **15**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

ppl1_clamp
==========

ppl1_clamp - Enable or disable package power clamping for limit #1

Synopsis
--------

| pepc power *info* **--ppl1-clamp**
| pepc power *config* **--ppl1-clamp**\ =<on|off>

Description
-----------

Enable or disable package power clamping for limit #1.

Mechanism
---------

MSR_PKG_POWER_LIMIT (**0x610**), bit **16**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

ppl1_window
===========

ppl1_window - RAPL package power limit #1 window size in seconds

Synopsis
--------

| pepc power *info* **--ppl1-window**

Description
-----------

RAPL package power limit #1 window size in seconds.

Mechanism
---------

MSR_PKG_POWER_LIMIT (**0x610**), bit **23:17**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

ppl2
====

ppl2 - RAPL package power limit #2 value in Watts

Synopsis
--------

| pepc power *info* **--ppl2**
| pepc power *config* **--ppl2**\ =<value>

Description
-----------

Average power usage limit of the package domain corresponding to time window #2.

Mechanism
---------

MSR_PKG_POWER_LIMIT (**0x610**), bits **46:32**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

ppl2_enable
===========

ppl2_enable - Enable or disable RAPL package power limit #2

Synopsis
--------

| pepc power *info* **--ppl2-enable**
| pepc power *config* **--ppl2-enable**\ =<on|off>

Description
-----------

Enable or disable RAPL package power limit #2.

Mechanism
---------

MSR_PKG_POWER_LIMIT (**0x610**), bit **47**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

ppl2_clamp
==========

ppl2_clamp - Enable or disable package power clamping for limit #2

Synopsis
--------

| pepc power *info* **--ppl2-clamp**
| pepc power *config* **--ppl2-clamp**\ =<on|off>

Description
-----------

Enable or disable package power clamping for limit #2.

Mechanism
---------

MSR_PKG_POWER_LIMIT (**0x610**), bit **48**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

ppl2_window
===========

ppl2_window - RAPL package power limit #2 window size in seconds

Synopsis
--------

| pepc power *info* **--ppl2-window**

Description
-----------

RAPL package power limit #2 window size in seconds.

Mechanism
---------

MSR_PKG_POWER_LIMIT (**0x610**), bit **55:49**.

Scope
-----

This option has **package** scope.
