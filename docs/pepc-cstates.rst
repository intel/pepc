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
   from the source directory, which includes datasets for many different systems.

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
   1. Use the special keyword 'all' to specify all cores. This option has to be accompanied by
   '--package' option, because core numbers are per-package

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

**--override-cpu-model**
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**--cstates** *[CSTATES]*
   Comma-separated list of C-states to get information about. C-states should be specified by name
   (e.g., 'C1'). Use 'all' to specify all the available Linux C-states (this is the default). Note,
   there is a difference between Linux C-states (e.g., 'C6') and hardware C-states (e.g., Core C6 or
   Package C6 on many Intel platforms). The former is what Linux can request, and on Intel hardware
   this is usually about various 'mwait' instruction hints. The latter are platform-specific
   hardware state, entered upon a Linux request.

**--pkg-cstate-limit**
   Get package C-state limit (details in 'pkg_cstate_limit_').

**--c1-demotion**
   Get current setting for C1 demotion (details in 'c1_demotion_').

**--c1-undemotion**
   Get current setting for C1 undemotion (details in 'c1_undemotion_').

**--c1e-autopromote**
   Get current setting for C1E autopromote (details in 'c1e_autopromote_').

**--cstate-prewake**
   Get current setting for C-state prewake (details in 'cstate_prewake_').

**--idle-driver**
   Get idle driver (details in 'idle_driver_').

**--governor**
   Get idle governor (details in 'governor_').


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
   12. Use the special keyword 'all' to specify all cores. This option has to be accompanied by
   '--package' option, because core numbers are per-package

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

**--override-cpu-model**
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**--enable** *[CSTATES]*
   Comma-separated list of C-states to enable. C-states should be specified by name (e.g., 'C1').
   Use 'all' to specify all the available Linux C-states (this is the default). Note, there is a
   difference between Linux C-states (e.g., 'C6') and hardware C-states (e.g., Core C6 or Package C6
   on many Intel platforms). The former is what Linux can request, and on Intel hardware this is
   usually about various 'mwait' instruction hints. The latter are platform-specific hardware state,
   entered upon a Linux request.

**--disable** *[CSTATES]*
   Similar to '--enable', but specifies the list of C-states to disable.

**--pkg-cstate-limit** *[PKG_CSTATE_LIMIT]*
   Set package C-state limit (details in 'pkg_cstate_limit_').

**--c1-demotion** *[C1_DEMOTION]*
   Enable or disable C1 demotion (details in 'c1_demotion_').

**--c1-undemotion** *[C1_UNDEMOTION]*
   Enable or disable C1 undemotion (details in 'c1_undemotion_').

**--c1e-autopromote** *[C1E_AUTOPROMOTE]*
   Enable or disable C1E autopromote (details in 'c1e_autopromote_').

**--cstate-prewake** *[CSTATE_PREWAKE]*
   Enable or disable C-state prewake (details in 'cstate_prewake_').

**--governor** *[GOVERNOR]*
   Set idle governor (details in 'governor_').

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

| pepc cstates *info* [**--pkg-cstate-limit**]
| pepc cstates *config* [**--pkg-cstate-limit**\ =<value>]

Description
-----------

The deepest package C-state the platform is allowed to enter. MSR_PKG_CST_CONFIG_CONTROL (**0xE2**)
register can be locked by the BIOS, in which case the package C-state limit can only be read, but
cannot be modified.

Source
------

MSR_PKG_CST_CONFIG_CONTROL (**0xE2**)

Package C-state limits are documented in Intel SDM, but it describes all the possible package
C-states for a CPU model. In practice, however, specific platforms often do not support many of
package C-states. For example, Xeons typically do not support anything deeper than PC6.

Refer to 'PCStateConfigCtl.py' for all platforms and bits.

Scope
-----

This option has **core** scope. With the following exceptions, Silvermonts and Airmonts have
**module** scope, Xeon Phis have **package** scope.

----------------------------------------------------------------------------------------------------

c1_demotion
===========

c1_demotion - C1 demotion

Synopsis
--------

| pepc cstates *info* [**--c1-demotion**]
| pepc cstates *config* [**--c1-demotion**\ =<value>]

Description
-----------

Allow or disallow the CPU to demote **C6** or **C7** requests to **C1**.

Source
------

MSR_PKG_CST_CONFIG_CONTROL (**0xE2**), bit **26**.

Scope
-----

This option has **core** scope. With the following exceptions, Silvermonts and Airmonts have
**module** scope, Xeon Phis have **package** scope.

----------------------------------------------------------------------------------------------------

c1_undemotion
=============

c1_demotion - C1 undemotion

Synopsis
--------

| pepc cstates *info* [**--c1-undemotion**]
| pepc cstates *config* [**--c1-undemotion**\ =<value>]

Description
-----------

Allow or disallow the CPU to un-demote previously demoted requests back from **C1** to
**C6** or **C7**.

Source
------

MSR_PKG_CST_CONFIG_CONTROL (**0xE2**), bit **28**.

Scope
-----

This option has **core** scope. With the following exceptions, Silvermonts and Airmonts have
**module** scope, Xeon Phis have **package** scope.

----------------------------------------------------------------------------------------------------

c1e_autopromote
===============

c1e_autopromote - C1E autopromote

Synopsis
--------

| pepc cstates *info* [**--c1e-autopromote**]
| pepc cstates *config* [**--c1e-autopromote**\ =<value>]

Description
-----------

When enabled, the CPU automatically converts all **C1** requests to **C1E** requests.

Source
------

MSR_POWER_CTL (**0x1FC**), bit **1**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

cstate_prewake
==============

cstate_prewake - C-state prewake

Synopsis
--------

| pepc cstates *info* [**--cstate-prewake**]
| pepc cstates *config* [**--cstate-prewake**\ =<value>]

Description
-----------

When enabled, the CPU will start exiting the **C6** idle state in advance, prior to the next local
APIC timer event.

Source
------

MSR_POWER_CTL (**0x1FC**), bit **30**.

Scope
-----

This option has **package** scope.

----------------------------------------------------------------------------------------------------

idle_driver
===========

idle_driver - Idle driver

Synopsis
--------

pepc cstates *info* [**--idle-driver**]

Description
-----------

Idle driver is responsible for enumerating and requesting the C-states available on the platform.

Source
------

"/sys/devices/system/cpu/cpuidle/current_governor"

Scope
-----

This option has **global** scope.

----------------------------------------------------------------------------------------------------

governor
========

governor - CPU frequency governor

Synopsis
--------

| pepc cstates *info* [**--governor**]
| pepc cstates *config* [**--governor**\ =<value>]

Description
-----------

CPU frequency governor decides which P-state to select on a CPU depending on CPU business and other
factors.

Source
------

"/sys/devices/system/cpu/cpuidle/scaling_governor"

Scope
-----

This option has **global** scope.
