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

COMMANDS
========

**pepc** *cpu-hotplug*
   CPU online/offline commands.

**pepc** *cstates*
   CPU C-state commands.

**pepc** *pstates*
   P-state commands.

**pepc** *aspm*
   PCI ASPM commands.

COMMAND *'pepc* cpu-hotplug'
============================

usage: pepc cpu-hotplug [-h] [-q] [-d] ...

CPU online/offline commands.

OPTIONS *'pepc* cpu-hotplug'
============================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

FURTHER SUB-COMMANDS *'pepc cpu-hotplug'*
=========================================

**pepc cpu-hotplug** *info*
   List online and offline CPUs.

**pepc cpu-hotplug** *online*
   Bring CPUs online.

**pepc cpu-hotplug** *offline*
   Bring CPUs offline.

COMMAND *'pepc* cpu-hotplug info'
=================================

usage: pepc cpu-hotplug info [-h] [-q] [-d]

List online and offline CPUs.

OPTIONS *'pepc* cpu-hotplug info'
=================================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

COMMAND *'pepc* cpu-hotplug online'
===================================

usage: pepc cpu-hotplug online [-h] [-q] [-d] [--cpus CPUS]

Bring CPUs online.

OPTIONS *'pepc* cpu-hotplug online'
===================================

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

COMMAND *'pepc* cpu-hotplug offline'
====================================

usage: pepc cpu-hotplug offline [-h] [-q] [-d] [--cpus CPUS] [--cores
CORES] [--packages PACKAGES] [--siblings]

Bring CPUs offline.

OPTIONS *'pepc* cpu-hotplug offline'
====================================

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
   Offline only "sibling CPUs", making sure there is only one logical
   CPU per core is left online. The sibling CPUs will be searched for
   among the CPUs selected with '--cpus', '--cores', and '--packages'.
   Therefore, specifying '--cpus all --siblings' will effectively
   disable hyper-threading on Intel CPUs.

COMMAND *'pepc* cstates'
========================

usage: pepc cstates [-h] [-q] [-d] ...

Various commands related to CPU C-states.

OPTIONS *'pepc* cstates'
========================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

FURTHER SUB-COMMANDS *'pepc cstates'*
=====================================

**pepc cstates** *info*
   Get CPU C-states information.

**pepc cstates** *config*
   Configure C-states.

COMMAND *'pepc* cstates info'
=============================

usage: pepc cstates info [-h] [-q] [-d] [--cstates CSNAMES] [--cpus
CPUS] [--cores CORES] [--packages PACKAGES]

Get information about C-states on specified CPUs (CPU0 by default).
Remember, this is information about the C-states that Linux can request,
they are not necessarily the same as the C-states supported by the
underlying hardware.

OPTIONS *'pepc* cstates info'
=============================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cstates** *CSNAMES*
   Comma-sepatated list of C-states to get information about (all
   C-states by default). C-states should be specified by name (e.g.,
   'C1'). Use 'all' to specify all the available Linux C-states (this is
   the default). Note, there is a difference between Linux C-states
   (e.g., 'C6') and hardware C-states (e.g., Core C6 or Package C6 on
   many Intel platforms). The former is what Linux can request, and on
   Intel hardware this is usually about various 'mwait' instruction
   hints. The latter are platform-specific hardware state, entered upon
   a Linux request..

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

COMMAND *'pepc* cstates config'
===============================

usage: pepc cstates config [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--enable [CSTATES]] [--disable [CSTATES]]
[--pkg-cstate-limit [PKG_CSTATE_LIMIT]] [--c1-demotion [C1_DEMOTION]]
[--c1-undemotion [C1_UNDEMOTION]] [--c1e-autopromote [C1E_AUTOPROMOTE]]
[--cstate-prewake [CSTATE_PREWAKE]]

Configure C-states on specified CPUs. All options can be used without a
parameter, in which case the currently configured value(s) will be
printed.

OPTIONS *'pepc* cstates config'
===============================

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

**--enable** *[CSTATES]*
   Comma-sepatated list of C-states to enable. C-states should be
   specified by name (e.g., 'C1'). Use 'all' to specify all the
   available Linux C-states (this is the default). Note, there is a
   difference between Linux C-states (e.g., 'C6') and hardware C-states
   (e.g., Core C6 or Package C6 on many Intel platforms). The former is
   what Linux can request, and on Intel hardware this is usually about
   various 'mwait' instruction hints. The latter are platform-specific
   hardware state, entered upon a Linux request..

**--disable** *[CSTATES]*
   Similar to '--enable', but specifies the list of C-states to disable.

**--pkg-cstate-limit** *[PKG_CSTATE_LIMIT]*
   Set Package C-state limit. The deepest package C-state the platform
   is allowed to enter. The package C-state limit is configured via MSR
   {MSR_PKG_CST_CONFIG_CONTROL:#x} (MSR_PKG_CST_CONFIG_CONTROL). This
   model-specific register can be locked by the BIOS, in which case the
   package C-state limit can only be read, but cannot be modified.
   Package C-state limit has package scope.

**--c1-demotion** *[C1_DEMOTION]*
   Enable or disable C1 demotion. Allow/disallow the CPU to demote C6/C7
   requests to C1. Use "on" or "off". C1 demotion has core scope.

**--c1-undemotion** *[C1_UNDEMOTION]*
   Enable or disable C1 undemotion. Allow/disallow the CPU to un-demote
   previously demoted requests back from C1 to C6/C7. Use "on" or "off".
   C1 undemotion has core scope.

**--c1e-autopromote** *[C1E_AUTOPROMOTE]*
   Enable or disable C1E autopromote. When enabled, the CPU
   automatically converts all C1 requests to C1E requests. This CPU
   feature is controlled by MSR 0x1fc, bit 1. Use "on" or "off". C1E
   autopromote has package scope.

**--cstate-prewake** *[CSTATE_PREWAKE]*
   Enable or disable C-state prewake. When enabled, the CPU will start
   exiting the C6 idle state in advance, prior to the next local APIC
   timer event. This CPU feature is controlled by MSR 0x1fc, bit 30. Use
   "on" or "off". C-state prewake has package scope.

COMMAND *'pepc* pstates'
========================

usage: pepc pstates [-h] [-q] [-d] ...

Various commands related to P-states (CPU performance states).

OPTIONS *'pepc* pstates'
========================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

FURTHER SUB-COMMANDS *'pepc pstates'*
=====================================

**pepc pstates** *info*
   Get P-states information.

**pepc pstates** *config*
   Configure other P-state aspects.

COMMAND *'pepc* pstates info'
=============================

usage: pepc pstates info [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--uncore]

Get P-states information for specified CPUs (CPU0 by default).

OPTIONS *'pepc* pstates info'
=============================

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

COMMAND *'pepc* pstates config'
===============================

usage: pepc pstates config [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--min-freq [MINFREQ]] [--max-freq [MAXFREQ]]
[--min-uncore-freq [MINUFREQ]] [--max-uncore-freq [MAXUFREQ]] [--epb
[EPB]] [--epp [EPP]] [--governor [GOVERNOR]] [--turbo [{on,off}]]

Configure P-states on specified CPUs

OPTIONS *'pepc* pstates config'
===============================

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

**--min-freq** *[MINFREQ]*
   Set minimum CPU frequency. The default unit is 'kHz', but 'Hz',
   'MHz', and 'GHz' can also be used, for example '900MHz'.
   Additionally, one of the following specifiers can be used: min,lfm -
   minimum supported frequency (LFM), eff - maximum efficiency
   frequency, base,hfm - base frequency (HFM), max - maximum supported
   frequency. Applies to all CPUs by default.

**--max-freq** *[MAXFREQ]*
   Same as '--min-freq', but for maximum CPU frequency.

**--min-uncore-freq** *[MINUFREQ]*
   Set minimum uncore frequency. The default unit is 'kHz', but 'Hz',
   'MHz', and 'GHz' can also be used, for example '900MHz'.
   Additionally, one of the following specifiers can be used: 'min' -
   the minimum supported uncore frequency, 'max' - the maximum supported
   uncore frequency. Uncore frequency is per-package, therefore, the
   '--cpus' and '--cores' options should not be used with this option.
   Applies to all packages by default.

**--max-uncore-freq** *[MAXUFREQ]*
   Same as '--min-uncore-freq', but for maximum uncore frequency.

**--epb** *[EPB]*
   Set energy performance bias hint. Hint can be integer in range of
   [0,15]. By default this option applies to all CPUs.

**--epp** *[EPP]*
   Set energy performance preference. Preference can be integer in range
   of [0,255], or policy string. By default this option applies to all
   CPUs.

**--governor** *[GOVERNOR]*
   Set CPU scaling governor. By default this option applies to all CPUs.

**--turbo** *[{on,off}]*
   Enable or disable turbo mode. Turbo on/off is global.

COMMAND *'pepc* aspm'
=====================

usage: pepc aspm [-h] [-q] [-d] ...

Manage Active State Power Management configuration.

OPTIONS *'pepc* aspm'
=====================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

FURTHER SUB-COMMANDS *'pepc aspm'*
==================================

**pepc aspm** *info*
   Get PCI ASPM information.

**pepc aspm** *config*
   Change PCI ASPM configuration.

COMMAND *'pepc* aspm info'
==========================

usage: pepc aspm info [-h] [-q] [-d]

Get information about current PCI ASPM configuration.

OPTIONS *'pepc* aspm info'
==========================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

COMMAND *'pepc* aspm config'
============================

usage: pepc aspm config [-h] [-q] [-d] [--policy [POLICY]]

Change PCI ASPM configuration.

OPTIONS *'pepc* aspm config'
============================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--policy** *[POLICY]*
   the PCI ASPM policy to set, use "default" to set the Linux default
   policy.

AUTHORS
=======

**pepc** was written by Artem Bityutskiy <dedekind1@gmail.com>.

DISTRIBUTION
============

The latest version of pepc may be downloaded from
` <https://github.com/intel/pepc>`__
