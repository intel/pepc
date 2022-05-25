====
PEPC
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
PRIVKEY] [-T TIMEOUT] [--force-color] {cpu-hotplug,cstates,pstates,aspm}
...

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
   paths like

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

usage: pepc cpu-hotplug [-h] [-q] [-d] {info,online,offline} ...

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
   Therefore, specifying '-- cpus all --siblings' will effectively
   disable hyper-threading on Intel CPUs.

COMMAND *'pepc* cstates'
========================

usage: pepc cstates [-h] [-q] [-d] {info,config} ...

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

usage: pepc cstates info [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--cstates CSNAMES] [--pkg-cstate-limit]
[--c1-demotion] [--c1-undemotion] [--c1e-autopromote] [--cstate-prewake]

Get information about C-states on specified CPUs. By default, prints all
information for all CPUs. Remember, this is information about the
C-states that Linux can request, they are not necessarily the same as
the C-states supported by the underlying hardware.

OPTIONS *'pepc* cstates info'
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
   the special keyword 'all' to specify all CPUs. If the
   CPUs/cores/packages were not specified, all CPUs will be used as the
   default value.

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

**--pkg-cstate-limit**
   Get package C-state limit. The deepest package C-state the platform
   is allowed to enter. The package C-state limit is configured via MSR
   {MSR_PKG_CST_CONFIG_CONTROL:#x} (MSR_PKG_CST_CONFIG_CONTROL). This
   model- specific register can be locked by the BIOS, in which case the
   package C-state limit can only be read, but cannot be modified. This
   option has package scope.

**--c1-demotion**
   Get current setting for c1 demotion. Allow/disallow the CPU to demote
   C6/C7 requests to C1. This option has core scope.

**--c1-undemotion**
   Get current setting for c1 undemotion. Allow/disallow the CPU to
   un-demote previously demoted requests back from C1 to C6/C7. This
   option has core scope.

**--c1e-autopromote**
   Get current setting for c1E autopromote. When enabled, the CPU
   automatically converts all C1 requests to C1E requests. This CPU
   feature is controlled by MSR 0x1fc, bit 1. This option has package
   scope.

**--cstate-prewake**
   Get current setting for c-state prewake. When enabled, the CPU will
   start exiting the C6 idle state in advance, prior to the next local
   APIC timer event. This CPU feature is controlled by MSR 0x1fc, bit
   30. This option has package scope.

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
   'all' to specify all CPUs. If the CPUs/cores/packages were not
   specified, all CPUs will be used as the default value.

**--cores** *CORES*
   List of cores to configure. The list can include individual core
   numbers and core number ranges. For example, '1-4,7,8,10-12' would
   mean cores 1 to 4, cores 7, 8, and 10 to 12. Use the special keyword
   'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to configure. The list can include individual
   package numbers and package number ranges. For example, '1-3' would
   mean packages 1 to 3, and

all packages.

**--enable** *[CSTATES]*
   Comma-sepatated list of C-states to enable. C-states should be
   specified by name (e.g., 'C1'). Use 'all' to specify all the
   available Linux C-states (this is the default). Note, there is a
   difference between Linux C-states (e.g.,

platforms). The former is what Linux can request, and on Intel hardware
this is usually about various 'mwait' instruction hints. The latter are
platform- specific hardware state, entered upon a Linux request..

**--disable** *[CSTATES]*
   Similar to '--enable', but specifies the list of C-states to disable.

**--pkg-cstate-limit** *[PKG_CSTATE_LIMIT]*
   Set package C-state limit. The deepest package C-state the platform
   is allowed to enter. The package C-state limit is configured via MSR
   {MSR_PKG_CST_CONFIG_CONTROL:#x} (MSR_PKG_CST_CONFIG_CONTROL). This
   model- specific register can be locked by the BIOS, in which case the
   package C-state limit can only be read, but cannot be modified. This
   option has package scope.

**--c1-demotion** *[C1_DEMOTION]*
   Enable or disable c1 demotion. Allow/disallow the CPU to demote C6/C7
   requests to C1. Use "on" or "off". This option has core scope.

**--c1-undemotion** *[C1_UNDEMOTION]*
   Enable or disable c1 undemotion. Allow/disallow the CPU to un-demote
   previously demoted requests back from C1 to C6/C7. Use "on" or "off".
   This option has core scope.

**--c1e-autopromote** *[C1E_AUTOPROMOTE]*
   Enable or disable c1E autopromote. When enabled, the CPU
   automatically converts all C1 requests to C1E requests. This CPU
   feature is controlled by MSR 0x1fc, bit 1. Use "on" or "off". This
   option has package scope.

**--cstate-prewake** *[CSTATE_PREWAKE]*
   Enable or disable c-state prewake. When enabled, the CPU will start
   exiting the C6 idle state in advance, prior to the next local APIC
   timer event. This CPU feature is controlled by MSR 0x1fc, bit 30. Use
   "on" or "off". This option has package scope.

COMMAND *'pepc* pstates'
========================

usage: pepc pstates [-h] [-q] [-d] {info,config} ...

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
   Configure P-states.

COMMAND *'pepc* pstates info'
=============================

usage: pepc pstates info [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--min-freq] [--max-freq] [--min-freq-limit]
[--max-freq-limit] [--base-freq] [--max-eff-freq] [--turbo]
[--max-turbo-freq] [--min-uncore-freq] [--max-uncore-freq]
[--min-uncore-freq-limit] [--max-uncore-freq-limit] [--hwp] [--epp]
[--epp-policy] [--epb] [--epb-policy] [--driver] [--governor]

Get P-states information for specified CPUs. By default, prints all
information for all CPUs.

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
   the special keyword 'all' to specify all CPUs. If the
   CPUs/cores/packages were not specified, all CPUs will be used as the
   default value.

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

**--min-freq**
   Get minimum CPU frequency. Minimum frequency the operating system
   will configure the CPU to run at. This option has CPU scope.

**--max-freq**
   Get maximum CPU frequency. Maximum frequency the operating system
   will configure the CPU to run at. This option has CPU scope.

**--min-freq-limit**
   Get minimum supported CPU frequency. Minimum supported CPU frequency.
   This option has CPU scope.

**--max-freq-limit**
   Get maximum supported CPU frequency. Maximum supported CPU frequency.
   This option has CPU scope.

**--base-freq**
   Get base CPU frequency. Base CPU frequency. This option has CPU
   scope.

**--max-eff-freq**
   Get maximum CPU efficiency frequency. Maximum energy efficient CPU
   frequency. This option has CPU scope.

**--turbo**
   Get current setting for turbo. When turbo is enabled, the CPUs can
   automatically run at a frequency greater than base frequency. This
   option has global scope.

**--max-turbo-freq**
   Get maximum CPU turbo frequency. Maximum frequency CPU can run at in
   turbo mode. This option has CPU scope.

**--min-uncore-freq**
   Get minimum uncore frequency. Minimum frequency the operating system
   will configure the uncore to run at. This option has die scope.

**--max-uncore-freq**
   Get maximum uncore frequency. Maximum frequency the operating system
   will configure the uncore to run at. This option has die scope.

**--min-uncore-freq-limit**
   Get minimum supported uncore frequency. Minimum supported uncore
   frequency This option has die scope.

**--max-uncore-freq-limit**
   Get maximum supported uncore frequency. Maximum supported uncore
   frequency This option has die scope.

**--hwp**
   Get current setting for hardware power mangement. When hardware power
   management is enabled, CPUs can automatically scale their frequency
   without active OS involemenent. This option has global scope.

**--epp**
   Get energy Performance Preference. Energy Performance Preference
   (EPP) is a hint to the CPU on energy efficiency vs performance. EPP
   has an effect only when the CPU is in the hardware power management
   (HWP) mode. This option has CPU scope.

**--epp-policy**
   Get EPP policy. EPP policy is a name, such as 'performance', which
   Linux maps to an EPP value, which may depend on the platform. This
   option has CPU scope.

**--epb**
   Get energy Performance Bias. Energy Performance Bias (EPB) is a hint
   to the CPU on energy efficiency vs performance. Value 0 means maximum
   performance, value 15 means maximum energy efficiency. EPP may have
   an effect in both HWP enabled and disabled modes (HWP stands for
   Hardware Power Management). This option has CPU scope.

**--epb-policy**
   Get EPB policy. EPB policy is a name, such as 'performance', which
   Linux maps to an EPB value, which may depend on the platform. This
   option has CPU scope.

**--driver**
   Get CPU frequency driver. Linux CPU frequency driver name. This
   option has global scope.

**--governor**
   Get CPU frequency governor. Linux CPU frequency governor name. This
   option has CPU scope.

COMMAND *'pepc* pstates config'
===============================

usage: pepc pstates config [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--min-freq [MIN_FREQ]] [--max-freq [MAX_FREQ]]
[--turbo [TURBO]] [--min-uncore-freq [MIN_UNCORE_FREQ]]
[--max-uncore-freq [MAX_UNCORE_FREQ]] [--epp [EPP]] [--epp-policy
[EPP_POLICY]] [--epb [EPB]] [--epb-policy [EPB_POLICY]] [--governor
[GOVERNOR]]

Configure P-states on specified CPUs. All options can be used without a
parameter, in which case the currently configured value(s) will be
printed.

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
   the special keyword 'all' to specify all CPUs. If the
   CPUs/cores/packages were not specified, all CPUs will be used as the
   default value.

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

**--min-freq** *[MIN_FREQ]*
   Set minimum CPU frequency. Minimum frequency the operating system
   will configure the CPU to run at. The default unit is 'Hz', but
   'kHz', 'MHz', and

**--max-freq** *[MAX_FREQ]*
   Set maximum CPU frequency. Maximum frequency the operating system
   will configure the CPU to run at. The default unit is 'Hz', but
   'kHz', 'MHz', and

**--turbo** *[TURBO]*
   Enable or disable turbo. When turbo is enabled, the CPUs can
   automatically run at a frequency greater than base frequency. Use
   "on" or "off". This option has global scope.

**--min-uncore-freq** *[MIN_UNCORE_FREQ]*
   Set minimum uncore frequency. Minimum frequency the operating system
   will configure the uncore to run at. The default unit is 'Hz', but
   'kHz', 'MHz', and 'GHz' can also be used, for example '900MHz'. This
   option has die scope.

**--max-uncore-freq** *[MAX_UNCORE_FREQ]*
   Set maximum uncore frequency. Maximum frequency the operating system
   will configure the uncore to run at. The default unit is 'Hz', but
   'kHz', 'MHz', and 'GHz' can also be used, for example '900MHz'. This
   option has die scope.

**--epp** *[EPP]*
   Set energy Performance Preference. Energy Performance Preference
   (EPP) is a hint to the CPU on energy efficiency vs performance. EPP
   has an effect only when the CPU is in the hardware power management
   (HWP) mode. This option has CPU scope.

**--epp-policy** *[EPP_POLICY]*
   Set EPP policy. EPP policy is a name, such as 'performance', which
   Linux maps to an EPP value, which may depend on the platform. This
   option has CPU scope.

**--epb** *[EPB]*
   Set energy Performance Bias. Energy Performance Bias (EPB) is a hint
   to the CPU on energy efficiency vs performance. Value 0 means maximum
   performance, value 15 means maximum energy efficiency. EPP may have
   an effect in both HWP enabled and disabled modes (HWP stands for
   Hardware Power Management). This option has CPU scope.

**--epb-policy** *[EPB_POLICY]*
   Set EPB policy. EPB policy is a name, such as 'performance', which
   Linux maps to an EPB value, which may depend on the platform. This
   option has CPU scope.

**--governor** *[GOVERNOR]*
   Set CPU frequency governor. Linux CPU frequency governor name. This
   option has CPU scope.

COMMAND *'pepc* aspm'
=====================

usage: pepc aspm [-h] [-q] [-d] {info,config} ...

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

::

   Artem Bityutskiy

dedekind1@gmail.com

DISTRIBUTION
============

The latest version of pepc may be downloaded from
` <https://github.com/intel/pepc>`__
