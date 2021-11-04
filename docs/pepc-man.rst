====
pepc
====

:Date:   Manual

.. contents::
   :depth: 3
..

NAME
====

pepc

SYNOPSIS
========

**pepc** [-h] [-q] [-d] [--version] [-H HOSTNAME] [-U USERNAME] [-K
PRIVKEY] [-T TIMEOUT] [--force-color] ...

DESCRIPTION
===========

pepc - Power, Energy, and Performance Configuration tool for Linux.

OPTIONS
=======

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--version**
   Print version and exit.

**-H** *HOSTNAME*, **--host** *HOSTNAME*
   Name of the host to run the command on.

**-U** *USERNAME*, **--username** *USERNAME*
   Name of the user to use for logging into the remote host over SSH.
   The default user name is 'root'.

**-K** *PRIVKEY*, **--priv-key** *PRIVKEY*
   Path to the private SSH key that should be used for logging into the
   remote host. By default the key is automatically found from standard
   paths like '~/.ssh'.

**-T** *TIMEOUT*, **--timeout** *TIMEOUT*
   SSH connect timeout in seconds, default is 8.

**--force-color**
   Force coloring of the text output.

**Sub-commands**
----------------

**pepc** *cpu-hotplug*
   CPU online/offline commands.

**pepc** *cstates*
   CPU C-state commands.

**pepc** *pstates*
   P-state commands.

**pepc** *aspm*
   PCI ASPM commands.

OPTIONS 'pepc cpu-hotplug'
==========================

usage: pepc cpu-hotplug [-h] [-q] [-d] ...

CPU online/offline commands.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**Sub-commands**
----------------

**pepc cpu-hotplug** *info*
   List online and offline CPUs.

**pepc cpu-hotplug** *online*
   Bring CPUs online (all CPUs by default).

**pepc cpu-hotplug** *offline*
   Bring CPUs offline (all CPUs by default).

OPTIONS 'pepc cpu-hotplug info'
===============================

usage: pepc cpu-hotplug info [-h] [-q] [-d]

List online and offline CPUs.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

OPTIONS 'pepc cpu-hotplug online'
=================================

usage: pepc cpu-hotplug online [-h] [-q] [-d] [--cpus CPUS]

Bring CPUs online (all CPUs by default).

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to online. The list can include individual CPU numbers
   and CPU number ranges. For example, '1-4,7,8,10-12' would mean CPUs 1
   to 4, CPUs 7, 8, and 10 to 12. Use the special keyword 'all' to
   specify all CPUs.

OPTIONS 'pepc cpu-hotplug offline'
==================================

usage: pepc cpu-hotplug offline [-h] [-q] [-d] [--cpus CPUS] [--cores
CORES] [--packages PACKAGES] [--siblings]

Bring CPUs offline (all CPUs by default).

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to offline. The list can include individual CPU numbers
   and CPU number ranges. For example, '1-4,7,8,10-12' would mean CPUs 1
   to 4, CPUs 7, 8, and 10 to 12. Use the special keyword 'all' to
   specify all CPUs.

**--cores** *CORES*
   Same as '--cpus', but specifies list of cores.

**--packages** *PACKAGES*
   Same as '--cpus', but specifies list of packages.

**--siblings**
   Offline all sibling CPUs, making sure there is only one logical CPU
   per core left online. If none of '--cpus', '--cores', '--package'
   options were specified, this option effectively disables
   hyper-threading. Otherwise, this option will find all sibling CPUs
   among the selected CPUs, and disable all siblings except for the
   first sibling in each group of CPUs belonging to the same core.

OPTIONS 'pepc cstates'
======================

usage: pepc cstates [-h] [-q] [-d] ...

Various commands related to CPU C-states.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**Sub-commands**
----------------

**pepc cstates** *info*
   Get CPU C-states information.

**pepc cstates** *set*
   Enable or disable C-states.

**pepc cstates** *config*
   Configure other C-state aspects.

OPTIONS 'pepc cstates info'
===========================

usage: pepc cstates info [-h] [-q] [-d] [--cstates CSTATES] [--cpus
CPUS] [--cores CORES] [--packages PACKAGES]

Get information about C-states on specified CPUs (CPU0 by default).
Remember, this is information about the C-states that Linux can request,
they are not necessarily the same as the C-states supported by the
underlying hardware.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cstates** *CSTATES*
   Comma-sepatated list of C-states to get information about (all
   C-states by default). You can specify C-states either by name (e.g.,
   'C1') or by the index. Use 'all' to specify all the available
   C-states (this is the default).

**--cpus** *CPUS*
   List of CPUs to get information about. The list can include
   individual CPU numbers and CPU number ranges. For example,
   '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use
   the special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to get information about. The list can include
   individual core numbers and core number ranges. For example,
   '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to get information about. The list can include
   individual package numbers and package number ranges. For example,
   '1-3' would mean packages 1 to 3, and '1,3' would mean packages 1 and
   3. Use the special keyword 'all' to specify all packages.

OPTIONS 'pepc cstates set'
==========================

usage: pepc cstates set [-h] [-q] [-d] [--enable ENABLE] [--disable
DISABLE] [--cpus CPUS] [--cores CORES] [--packages PACKAGES]

Enable or disable specified C-states on specified CPUs (all CPUs by
default). Note, C-states will be enabled/disabled in the same order as
the '--enable' and '--disable' options are specified.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--enable** *ENABLE*
   Comma-sepatated list of C-states to enable (all by default). You can
   specify C-states either by name (e.g., 'C1') or by the index. Use
   'all' to specify all the available C-states (this is the default).

**--disable** *DISABLE*
   Similar to '--enable', but specifies the list of C-states to disable.

**--cpus** *CPUS*
   List of CPUs to enable the specified C-states on. The list can
   include individual CPU numbers and CPU number ranges. For example,
   '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use
   the special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to enable the specified C-states on. The list can
   include individual core numbers and core number ranges. For example,
   '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to enable the specified C-states on. The list can
   include individual package numbers and package number ranges. For
   example, '1-3' would mean packages 1 to 3, and '1,3' would mean
   packages 1 and 3. Use the special keyword 'all' to specify all
   packages.

OPTIONS 'pepc cstates config'
=============================

usage: pepc cstates config [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--cstate-prewake [{on,off}]] [--c1e-autopromote
[{on,off}]] [--pkg-cstate-limit [PKG_CSTATE_LIMIT]] [--c1-demotion
[{on,off}]] [--c1-undemotion [{on,off}]]

Configure other C-state aspects.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to configure. The list can include individual CPU
   numbers and CPU number ranges. For example, '1-4,7,8,10-12' would
   mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the special keyword
   'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to configure. The list can include individual core
   numbers and core number ranges. For example, '1-4,7,8,10-12' would
   mean cores 1 to 4, cores 7, 8, and 10 to 12. Use the special keyword
   'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to configure. The list can include individual
   package numbers and package number ranges. For example, '1-3' would
   mean packages 1 to 3, and '1,3' would mean packages 1 and 3. Use the
   special keyword 'all' to specify all packages.

**--cstate-prewake** [{on,off}]
   Enable or disable C-state prewake (applicaple only to Intel CPU).
   When enabled, exit from C-state will start prior next event. This is
   possible only if time of next event is known, for example in case of
   local APIC timers. This command toggles MSR 0x1fc, bit 30. Use "on"
   or "off". C-state prewake setting has package scope. By default this
   option applies to all packages. If you do not pass any argument to
   "--cstate-prewake", it will print the current values.

**--c1e-autopromote** [{on,off}]
   Enable or disable C1E autopromote (applicaple only to Intel CPU).
   When enabled, the CPU automatically converts all C1 requests into C1E
   requests. This command toggles MSR 0x1fc, bit 1. Use "on" or "off".
   C1E autopromote setting has package scope. By default this option
   applies to all packages. If you do not pass any argument to
   "--c1e-autopromote", it will print the current values.

**--pkg-cstate-limit** [*PKG_CSTATE_LIMIT*]
   Set Package C-state limit (applicaple only to Intel CPU). The deepest
   package C-state the platform is allowed to enter. The package C-state
   limit is configured via MSR {hex(MSR_PKG_CST_CONFIG_CONTROL)}
   (MSR_PKG_CST_CONFIG_CONTROL). This model-specific register can be
   locked by the BIOS, in which case the package C-state limit can only
   be read, but cannot be modified. Package C-state limit setting has
   package scope. By default this option applies to all packages. If you
   do not pass any argument to "--pkg-cstate-limit", it will print the
   current values.

**--c1-demotion** [{on,off}]
   Enable or disable C1 demotion (applicaple only to Intel CPU).
   Allow/disallow the CPU to demote C6/C7 requests to C1. Use "on" or
   "off". C1 demotion setting has CPU scope. By default this option
   applies to all CPUs. If you do not pass any argument to
   "--c1-demotion", it will print the current values.

**--c1-undemotion** [{on,off}]
   Enable or disable C1 undemotion (applicaple only to Intel CPU).
   Allow/disallow the CPU to un-demote previously demoted requests back
   from C1 to C6/C7. Use "on" or "off". C1 undemotion setting has CPU
   scope. By default this option applies to all CPUs. If you do not pass
   any argument to "--c1-undemotion", it will print the current values.

OPTIONS 'pepc pstates'
======================

usage: pepc pstates [-h] [-q] [-d] ...

Various commands related to P-states (CPU performance states).

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**Sub-commands**
----------------

**pepc pstates** *info*
   Get P-states information.

**pepc pstates** *set*
   Set CPU or uncore frequency.

**pepc pstates** *config*
   Configure other P-state aspects.

OPTIONS 'pepc pstates info'
===========================

usage: pepc pstates info [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--uncore]

Get P-states information for specified CPUs (CPU0 by default).

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to get information about. The list can include
   individual CPU numbers and CPU number ranges. For example,
   '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use
   the special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to get information about. The list can include
   individual core numbers and core number ranges. For example,
   '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to get information about. The list can include
   individual package numbers and package number ranges. For example,
   '1-3' would mean packages 1 to 3, and '1,3' would mean packages 1 and
   3. Use the special keyword 'all' to specify all packages.

**--uncore**
   By default this command provides CPU (core) frequency (P-state)
   information, but if this option is used, it will provide uncore
   frequency information instead. The uncore includes the interconnect
   between the cores, the shared cache, and other resources shared
   between the cores. Uncore frequency is per-package, therefore, the
   '--cpus' and '--cores' options should not be used with this option.

OPTIONS 'pepc pstates set'
==========================

usage: pepc pstates set [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--min-freq MINFREQ] [--max-freq MAXFREQ]
[--min-uncore-freq MINUFREQ] [--max-uncore-freq MAXUFREQ]

Set CPU frequency for specified CPUs (all CPUs by default) or uncore
frequency for specified packages (all packages by default).

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to set frequencies for. The list can include individual
   CPU numbers and CPU number ranges. For example, '1-4,7,8,10-12' would
   mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the special keyword
   'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to set frequencies for. The list can include individual
   core numbers and core number ranges. For example, '1-4,7,8,10-12'
   would mean cores 1 to 4, cores 7, 8, and 10 to 12. Use the special
   keyword 'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to set frequencies for. The list can include
   individual package numbers and package number ranges. For example,
   '1-3' would mean packages 1 to 3, and '1,3' would mean packages 1 and
   3. Use the special keyword 'all' to specify all packages.

**--min-freq** *MINFREQ*
   Set minimum CPU frequency. The default unit is 'kHz', but 'Hz',
   'MHz', and 'GHz' can also be used, for example '900MHz'.
   Additionally, one of the following specifiers can be used: min,lfm -
   minimum supported frequency (LFM), eff - maximum effeciency
   frequency, base,hfm - base frequency (HFM), max - maximum supported
   frequency.

**--max-freq** *MAXFREQ*
   Same as '--min-freq', but for maximum CPU frequency.

**--min-uncore-freq** *MINUFREQ*
   Set minimum uncore frequency. The default unit is 'kHz', but 'Hz',
   'MHz', and 'GHz' can also be used, for example '900MHz'.
   Additionally, one of the following specifiers can be used: 'min' -
   the minimum supported uncore frequency, 'max' - the maximum supported
   uncore frequency. Uncore frequency is per-package, therefore, the
   '--cpus' and '--cores' options should not be used with this option.

**--max-uncore-freq** *MAXUFREQ*
   Same as '--min-uncore-freq', but for maximum uncore frequency.

OPTIONS 'pepc pstates config'
=============================

usage: pepc pstates config [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--epb [EPB]] [--epp [EPP]] [--governor
[GOVERNOR]] [--turbo [{on,off}]]

Configure P-states on specified CPUs.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to configure P-States on. The list can include
   individual CPU numbers and CPU number ranges. For example,
   '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use
   the special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to configure P-States on. The list can include
   individual core numbers and core number ranges. For example,
   '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to configure P-States on. The list can include
   individual package numbers and package number ranges. For example,
   '1-3' would mean packages 1 to 3, and '1,3' would mean packages 1 and
   3. Use the special keyword 'all' to specify all packages.

**--epb** [*EPB*]
   Set energy performance bias hint. Hint can be integer in range of
   [0,15]. By default this option applies to all CPUs.

**--epp** [*EPP*]
   Set energy performance preference. Preference can be integer in range
   of [0,255], or policy string. By default this option applies to all
   CPUs.

**--governor** [*GOVERNOR*]
   Set CPU scaling governor. By default this option applies to all CPUs.

**--turbo** [{on,off}]
   Enable or disable turbo mode. Turbo on/off is global.

OPTIONS 'pepc aspm'
===================

usage: pepc aspm [-h] [-q] [-d] ...

Manage Active State Power Management configuration.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**Sub-commands**
----------------

**pepc aspm** *info*
   Get PCI ASPM information.

**pepc aspm** *set*
   Change PCI ASPM configuration.

OPTIONS 'pepc aspm info'
========================

usage: pepc aspm info [-h] [-q] [-d]

Get information about currrent PCI ASPM configuration.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

OPTIONS 'pepc aspm set'
=======================

usage: pepc aspm set [-h] [-q] [-d] [--policy [POLICY]]

Change PCI ASPM configuration.

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--policy** [*POLICY*]
   Specify the PCI ASPM policy to be set, use "default" to set the
   policy to its default value.

AUTHORS
=======

**pepc** was written by Artem Bityutskiy <dedekind1@gmail.com>.

DISTRIBUTION
============

The latest version of pepc may be downloaded from
` <https://github.com/intel/pepc>`__
