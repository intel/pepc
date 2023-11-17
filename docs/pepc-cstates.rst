.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Date:   09-03-2023
:Title:  CSTATES

.. Contents::
   :depth: 2
..

===================
Command *'cstates'*
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

Subcommand *'info'*
===================

Get information about C-states on specified CPUs. By default, prints all information for all CPUs.

**--cpus** *CPUS*
   List of CPUs to get information about. The list can include individual CPU numbers and CPU number
   ranges. For example,'1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the
   special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to get information about. The list can include individual core numbers and
   core number ranges. For example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to
   12. Use the special keyword 'all' to specify all cores. This option has to be accompanied by
   '--package' option, because core numbers are per-package.

**--dies** *DIES*
   List of dies to get information about. The list can include individual die numbers and die number
   ranges. For example, '0-3,5' would mean dies 0 to 3, and die 5. Use the special keyword 'all' to
   specify all dies. This option has to be accompanied by '--package' option, because die numbers
   are per-package.

**--packages** *PACKAGES*
   List of packages to get information about. The list can include individual package numbers and
   package number ranges. For example, '0,2-4' would mean package 0 and packages 2 to 4. Use the
   special keyword 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to get information about. The list can include individual core
   sibling indices or index ranges. For example, core x includes CPUs 3 and 4, '0' would mean CPU 3
   and '1' would mean CPU 4. This option can only be used to reference online CPUs, because Linux
   does not provide topology information for offline CPUs. In the previous example if CPU 3 was
   offline, then '0' would mean CPU 4.

**--yaml**
   Print information in YAML format.

**--override-cpu-model** *MODEL*
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
    Comma-separated list of mechanisms that are allowed to be used for configuring C-states. Use
    '--list-mechanisms' to get the list of available mechanisms. Note, many options support only one
    mechanism (e.g., 'sysfs'), some may support multiple (e.g., 'sysfs' and 'msr'). The mechanisms
    are tried in the specified order. By default, all mechanisms are allowed and the most
    preferred mechanisms will be tried first.

**--list-mechanisms**
   List mechanisms available for reading C-states information.

**--cstates** *[CSTATES]*
   Comma-separated list of C-states to get information about. C-states should be specified by name
   (e.g., 'C1'). Use 'all' to specify all the available Linux C-states (this is the default). Note,
   there is a difference between Linux C-states (e.g., 'C6') and hardware C-states (e.g., Core C6 or
   Package C6 on many Intel platforms). The former is what Linux can request, and on Intel hardware
   this is usually about various 'mwait' instruction hints. The latter are platform-specific
   hardware state, entered upon a Linux request.

**--pkg-cstate-limit**
   Get package C-state limit (details in 'pkg_cstate_limit_'), available package C-state limits
   (details in 'pkg_cstate_limits_'), package C-state limit lock (details in
   'pkg_cstate_limit_lock_'), and package C-state limit aliases (details in
   'pkg_cstate_limit_aliases_').

**--c1-demotion**
   Check if C1 demotion is enabled or disabled (details in 'c1_demotion_').

**--c1-undemotion**
   Check if C1 undemotion is enabled or disabled (details in 'c1_undemotion_').

**--c1e-autopromote**
   Check if C1E autopromote is enabled or disabled (details in 'c1e_autopromote_').

**--cstate-prewake**
   Check if C-state prewake is enabled or disabled (details in 'cstate_prewake_').

**--idle-driver**
   Get idle driver (details in 'idle_driver_').

**--governor**
   Get idle governor (details in 'governor_').

**--governors**
   Get list of available idle governors (details in 'governors_').

Subcommand *'config'*
=====================

Configure C-states on specified CPUs. All options can be used without a parameter, in which case the
currently configured value(s) will be printed.

**--cpus** *CPUS*
   List of CPUs to configure C-States on. The list can include individual CPU numbers and CPU number
   ranges. For example,'1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the
   special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to configure C-States on. The list can include individual core numbers and
   core number ranges. For example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to
   1. Use the special keyword 'all' to specify all cores. This option has to be accompanied by
   '--package' option, because core numbers are per-package

**--dies** *DIES*
   List of dies to configure C-States on. The list can include individual die numbers and die number
   ranges. For example, '0-3,5' would mean dies 0 to 3, and die 5. Use the special keyword 'all' to
   specify all dies. This option has to be accompanied by '--package' option, because die numbers
   are per-package.

**--packages** *PACKAGES*
   List of packages to configure C-States on. The list can include individual package numbers and
   package number ranges. For example, '0,2-4' would mean package 0 and packages 2 to 4. Use the
   special keyword 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to configure C-States on. The list can include individual core
   sibling indices or index ranges. For example, core x includes CPUs 3 and 4, '0' would mean CPU 3
   and '1' would mean CPU 4. This option can only be used to reference online CPUs, because Linux
   does not provide topology information for offline CPUs. In the previous example if CPU 3 was
   offline, then '0' would mean CPU 4.

**--override-cpu-model** *MODEL*
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**--list-mechanisms**
   List mechanisms available for configuring C-states.

**--enable** *CSTATES*
   Comma-separated list of C-states to enable. C-states should be specified by name (e.g., 'C1').
   Use 'all' to specify all the available Linux C-states (this is the default). Note, there is a
   difference between Linux C-states (e.g., 'C6') and hardware C-states (e.g., Core C6 or Package C6
   on many Intel platforms). The former is what Linux can request, and on Intel hardware this is
   usually about various 'mwait' instruction hints. The latter are platform-specific hardware state,
   entered upon a Linux request.

**--disable** *CSTATES*
   Similar to '--enable', but specifies the list of C-states to disable.

**--pkg-cstate-limit** *PKG_CSTATE_LIMIT*
   Set package C-state limit (details in 'pkg_cstate_limit_').

**--c1-demotion** *on|off*
   Enable or disable C1 demotion (details in 'c1_demotion_').

**--c1-undemotion** *on|off*
   Enable or disable C1 undemotion (details in 'c1_undemotion_').

**--c1e-autopromote** *on|off*
   Enable or disable C1E autopromote (details in 'c1e_autopromote_').

**--cstate-prewake** *on|off*
   Enable or disable C-state prewake (details in 'cstate_prewake_').

**--governor** *NAME*
   Set idle governor (details in 'governor_').

**--pch-negotiation** *on|off*
   Enable or disable PCH negotiation (details in 'pch_negotiation_').

Subcommand *'save'*
===================

Save all the modifiable C-state settings into a file. This file can later be used for restoring
C-state settings with the 'pepc cstates restore' command.

**--cpus** *CPUS*
   List of CPUs to save C-state information about. The list can include individual CPU numbers and
   CPU number ranges. For example,'1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to save C-state information about. The list can include individual core numbers and
   core number ranges. For example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to
   12. Use the special keyword 'all' to specify all cores. This option has to be accompanied by
   '--package' option, because core numbers are per-package

**--packages** *PACKAGES*
   List of packages to save C-state information about. The list can include individual package
   numbers and package number ranges. For example, '0,2-4' would mean package 0 and packages 2 to 4.
   Use the special keyword 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to save C-state information about. The list can include individual
   core sibling indices or index ranges. For example, core x includes CPUs 3 and 4, '0' would mean
   CPU 3 and '1' would mean CPU 4. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the previous example if CPU 3
   was offline, then '0' would mean CPU 4.

**-o** *OUTFILE*, **--outfile** *OUTFILE*
   Name of the file to save the settings to.

Subcommand *'restore'*
======================

Restore C-state settings from a file previously created with the 'pepc cstates save' command.

**-f** *INFILE*, **--from** *INFILE*
   Name of the file from which to restore the settings from, use "-" to read from the standard
   output.

----------------------------------------------------------------------------------------------------

==========
Properties
==========

pkg_cstate_limit
================

pkg_cstate_limit - Package C-state limit

Synopsis
--------

| pepc cstates *info* **--pkg-cstate-limit**
| pepc cstates *config* **--pkg-cstate-limit**\ =<on|off>

Description
-----------

The deepest package C-state the platform is allowed to enter. MSR_PKG_CST_CONFIG_CONTROL (0xE2)
register can be locked, in which case the package C-state limit can only be read, but cannot be
modified (please, refer to '**pkg_cstate_limit_lock**' for more information).

Mechanism
---------

**msr**
MSR_PKG_CST_CONFIG_CONTROL (0xE2), bits 2:0 or 3:0, depending on CPU model.

Scope
-----

This option has core scope. Exceptions: module scope on Silvermonts and Airmonts, package scop on
Xeon Phi processors.

----------------------------------------------------------------------------------------------------

pkg_cstate_limits
=================

pkg_cstate_limits - Available package C-state limits

Synopsis
--------

pepc cstates *info* **--pkg-cstate-limits**

Description
-----------

All available package C-state limits.

Mechanism
---------

**doc**
Intel SDM (Software Developer Manual) and Intel EDS (External Design Specification).

Scope
-----

This option has global scope.

----------------------------------------------------------------------------------------------------

pkg_cstate_limit_lock
=====================

pkg_cstate_limit_lock - Package C-state limit lock

Synopsis
--------

pepc cstates *info* **--pkg-cstate-limit-lock**

Description
-----------

Whether the package C-state limit can be modified. When 'True', '**pkg_cstate_limit**' is
read-only.

Mechanism
---------

**msr**
MSR_PKG_CST_CONFIG_CONTROL (0xE2), bit 15.

Scope
-----

This option has package scope.

----------------------------------------------------------------------------------------------------


pkg_cstate_limit_aliases
========================

pkg_cstate_limit_aliases - Package C-state limit aliases

Synopsis
--------

pepc cstates *info* **--pkg-cstate-limit-aliases**

Description
-----------

Package C-state limit aliases. For example on Ice Lake Xeon, 'PC6' is an alias for 'PC6R'.

Mechanism
---------

**doc**
Intel SDM (Software Developer Manual) or Intel EDS (External Design Specification).

Scope
-----

This option has global scope.

----------------------------------------------------------------------------------------------------

c1_demotion
===========

c1_demotion - C1 demotion

Synopsis
--------

| pepc cstates *info* **--c1-demotion**
| pepc cstates *config* **--c1-demotion**\ =<on|off>

Description
-----------

Allow or disallow the CPU to demote 'C6' or 'C7' C-state requests to 'C1'.

Mechanism
---------

MSR_PKG_CST_CONFIG_CONTROL (0xE2), bit 26.

Scope
-----

This option has core scope. Exceptions: module scope on Silvermonts and Airmonts, package scope on
Xeon Phis.

----------------------------------------------------------------------------------------------------

c1_undemotion
=============

c1_demotion - C1 undemotion

Synopsis
--------

| pepc cstates *info* **--c1-undemotion**
| pepc cstates *config* **--c1-undemotion**\ =<on|off>

Description
-----------

Allow or disallow the CPU to un-demote previously demoted requests back from 'C1' C-state to
'C6' or 'C7l.

Mechanism
---------

**msr**
MSR_PKG_CST_CONFIG_CONTROL (0xE2), bit 28.

Scope
-----

This option has core scope. Exceptions: module scope on Silvermonts and Airmonts, package scope on
Xeon Phis.

----------------------------------------------------------------------------------------------------

c1e_autopromote
===============

c1e_autopromote - C1E autopromote

Synopsis
--------

| pepc cstates *info* **--c1e-autopromote**
| pepc cstates *config* **--c1e-autopromote**\ =<on|off>

Description
-----------

When enabled, the CPU automatically converts all 'C1' C-state requests to 'C1E' requests.

Mechanism
---------

**msr**
MSR_POWER_CTL (0x1FC), bit 1.

Scope
-----

This option has package scope.

----------------------------------------------------------------------------------------------------

cstate_prewake
==============

cstate_prewake - C-state prewake

Synopsis
--------

| pepc cstates *info* **--cstate-prewake**
| pepc cstates *config* **--cstate-prewake**\ =<on|off>

Description
-----------

When enabled, the CPU will start exiting the 'C6' C-state in advance, prior to the next local
APIC timer event.

Mechanism
---------

**msr**
MSR_POWER_CTL (0x1FC), bit 30.

Scope
-----

This option has package scope.

----------------------------------------------------------------------------------------------------

idle_driver
===========

idle_driver - Idle driver

Synopsis
--------

pepc cstates *info* **--idle-driver**

Description
-----------

Idle driver is responsible for enumerating and requesting the C-states available on the platform.

Mechanism
---------

**sysfs***
"/sys/devices/system/cpu/cpuidle/current_governor"

Scope
-----

This option has global scope.

----------------------------------------------------------------------------------------------------

governor
========

governor - Idle governor

Synopsis
--------

| pepc cstates *info* **--governor**
| pepc cstates *config* **--governor**\ =<name>

Description
-----------

Idle governor decides which C-state to request on an idle CPU.

Mechanism
---------

**sysfs**
"/sys/devices/system/cpu/cpuidle/scaling_governor"

Scope
-----

This option has global scope.

----------------------------------------------------------------------------------------------------

governors
=========

governors - Available idle governors

Synopsis
--------

pepc cstates *info* **--governors**

Description
-----------

Idle governors decide which C-state to request on an idle CPU. Different governors implement
different selection policy.

Mechanism
---------

**sysfs**
"/sys/devices/system/cpu/cpuidle/available_governors"

Scope
-----

This property has global scope.

----------------------------------------------------------------------------------------------------

pch_negotiation
===============

pch_negotiation - PCH negotiation

Synopsis
--------

| pepc cstates *info* **--pch-negotiation**
| pepc cstates *config* **--pch-negotiation**\ =<on|off>

Description
-----------

When enabled, processor's PCU (Power Control Unit) informs PCH (Platform Controller Hub) about
entering and exiting package C6 state (PC6). Depending on configuration, PCH may use this
information to minimize its interactions with the processor. This may improve PC6 residency and
drives idle power down.

Source
------

**msr**
MSR_POWER_CTL (0x1FC), bit 36.

Scope
-----

This option has global scope.
