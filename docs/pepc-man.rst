====
PEPC
====

:Date:   2023-02-23

.. contents::
   :depth: 3
..

NAME
====

pepc

SYNOPSIS
========

**pepc** [-h] [-q] [-d] [--version] [-H HOSTNAME] [-U USERNAME] [-K
PRIVKEY] [-T TIMEOUT] [-D DATASET] [--force-color]
{cpu-hotplug,cstates,pstates,aspm,topology} ...

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

**-D** *DATASET*, **--dataset** *DATASET*
   This option is for debugging and testing purposes only, it defines
   the dataset that will be used to emulate a host for running the
   command on. Please, specify dataset path or name. In the latter case,
   it will be searched for in the following locations:
   /home/abityuts/powerlab/git/pepc/pepctool/tests/data,
   $PEPC_DATA_PATH/tests/data, $HOME/.local/share/pepc/tests/data,
   /usr/local/share/pepc/tests/data, /usr/share/pepc/tests/data. Use
   'all' to specify all available datasets.

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

**pepc** *topology*
   CPU topology commands.

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
CORES] [--packages PACKAGES] [--core-siblings CORE_SIBLINGS]

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
   specify all CPUs. If the CPUs/cores/packages were not specified, all
   CPUs will be used as the default value.

**--cores** *CORES*
   List of cores to offline. The list can include individual core
   numbers and core number ranges. For example, '1-4,7,8,10-12' would
   mean cores 1 to 4, cores 7, 8, and 10 to 12. Use the special keyword
   'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to offline. The list can include individual package
   numbers and package number ranges. For example, '1-3' would mean
   packages 1 to 3, and '1,3' would mean packages 1 and 3. Use the
   special keyword 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to offline. The list can include
   individual core sibling indices or index ranges. For example, core x
   includes CPUs 3 and 4, '0' would mean CPU 3 and '1' would mean CPU 4.
   This option can only be used to reference online CPUs, because Linux
   does not provide topology information for offline CPUs. In the
   previous example if CPU 3 was offline, then '0' would mean CPU 4.

COMMAND *'pepc* cstates'
========================

usage: pepc cstates [-h] [-q] [-d] {info,config,save,restore} ...

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

**pepc cstates** *save*
   Save C-states settings.

**pepc cstates** *restore*
   Restore C-states settings.

COMMAND *'pepc* cstates info'
=============================

usage: pepc cstates info [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--core-siblings CORE_SIBLINGS] [--yaml]
[--cstates [CATATES]] [--pkg-cstate-limit] [--c1-demotion]
[--c1-undemotion] [--c1e-autopromote] [--cstate-prewake] [--idle-driver]
[--governor]

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

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to get information about. The list can
   include individual core sibling indices or index ranges. For example,
   core x includes CPUs 3 and 4, '0' would mean CPU 3 and '1' would mean
   CPU 4. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the
   previous example if CPU 3 was offline, then '0' would mean CPU 4.

**--yaml**
   Print information in YAML format.

**--cstates** *[CATATES]*
   Comma-separated list of C-states to get information about (all
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
   model-specific register can be locked by the BIOS, in which case the
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

**--idle-driver**
   Get idle driver. Idle driver is responsible for enumerating and
   requesting the C-states available on the platform. This option has
   global scope.

**--governor**
   Get idle governor. Idle governor decides which C-state to request on
   an idle CPU. This option has global scope.

COMMAND *'pepc* cstates config'
===============================

usage: pepc cstates config [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--core-siblings CORE_SIBLINGS] [--enable
[CSTATES]] [--disable [CSTATES]] [--pkg-cstate-limit [PKG_CSTATE_LIMIT]]
[--c1-demotion [C1_DEMOTION]] [--c1-undemotion [C1_UNDEMOTION]]
[--c1e-autopromote [C1E_AUTOPROMOTE]] [--cstate-prewake
[CSTATE_PREWAKE]] [--governor [GOVERNOR]]

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
   mean packages 1 to 3, and '1,3' would mean packages 1 and 3. Use the
   special keyword 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to configure. The list can include
   individual core sibling indices or index ranges. For example, core x
   includes CPUs 3 and 4, '0' would mean CPU 3 and '1' would mean CPU 4.
   This option can only be used to reference online CPUs, because Linux
   does not provide topology information for offline CPUs. In the
   previous example if CPU 3 was offline, then '0' would mean CPU 4.

**--enable** *[CSTATES]*
   Comma-separated list of C-states to enable. C-states should be
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
   Set package C-state limit. The deepest package C-state the platform
   is allowed to enter. The package C-state limit is configured via MSR
   {MSR_PKG_CST_CONFIG_CONTROL:#x} (MSR_PKG_CST_CONFIG_CONTROL). This
   model-specific register can be locked by the BIOS, in which case the
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

**--governor** *[GOVERNOR]*
   Set idle governor. Idle governor decides which C-state to request on
   an idle CPU. This option has global scope.

COMMAND *'pepc* cstates save'
=============================

usage: pepc cstates save [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--core-siblings CORE_SIBLINGS] [-o OUTFILE]

Save all the modifiable C-state settings into a file. This file can
later be used for restoring C-state settings with the 'pepc cstates
restore' command.

OPTIONS *'pepc* cstates save'
=============================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to save C-state information about. The list can include
   individual CPU numbers and CPU number ranges. For example,
   '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use
   the special keyword 'all' to specify all CPUs. If the
   CPUs/cores/packages were not specified, all CPUs will be used as the
   default value.

**--cores** *CORES*
   List of cores to save C-state information about. The list can include
   individual core numbers and core number ranges. For example,
   '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to save C-state information about. The list can
   include individual package numbers and package number ranges. For
   example, '1-3' would mean packages 1 to 3, and '1,3' would mean
   packages 1 and 3. Use the special keyword

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to save C-state information about. The
   list can include individual core sibling indices or index ranges. For
   example, core x includes CPUs 3 and 4, '0' would mean CPU 3 and '1'
   would mean CPU 4. This option can only be used to reference online
   CPUs, because Linux does not provide topology information for offline
   CPUs. In the previous example if CPU 3 was offline, then '0' would
   mean CPU 4.

**-o** *OUTFILE*, **--outfile** *OUTFILE*
   Name of the file to save the settings to.

COMMAND *'pepc* cstates restore'
================================

usage: pepc cstates restore [-h] [-q] [-d] [-f INFILE]

Restore C-state settings from a file previously created with the 'pepc
cstates save' command.

OPTIONS *'pepc* cstates restore'
================================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**-f** *INFILE*, **--from** *INFILE*
   Name of the file restore the settings from (use "-" to read from the
   standard output.

COMMAND *'pepc* pstates'
========================

usage: pepc pstates [-h] [-q] [-d] {info,config,save,restore} ...

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

**pepc pstates** *save*
   Save P-states settings.

**pepc pstates** *restore*
   Restore P-states settings.

COMMAND *'pepc* pstates info'
=============================

usage: pepc pstates info [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--core-siblings CORE_SIBLINGS] [--yaml]
[--min-freq] [--max-freq] [--min-freq-limit] [--max-freq-limit]
[--base-freq] [--min-freq-hw] [--max-freq-hw] [--min-oper-freq]
[--max-eff-freq] [--turbo] [--max-turbo-freq] [--min-uncore-freq]
[--max-uncore-freq] [--min-uncore-freq-limit] [--max-uncore-freq-limit]
[--hwp] [--epp] [--epp-hw] [--epb] [--epb-hw] [--driver]
[--intel-pstate-mode] [--governor]

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

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to get information about. The list can
   include individual core sibling indices or index ranges. For example,
   core x includes CPUs 3 and 4, '0' would mean CPU 3 and '1' would mean
   CPU 4. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the
   previous example if CPU 3 was offline, then '0' would mean CPU 4.

**--yaml**
   Print information in YAML format.

**--min-freq**
   Get min. CPU frequency. Minimum CPU frequency is the lowest frequency
   the operating system configured the CPU to run at (via sysfs knobs).
   The default unit is "Hz", but "kHz", "MHz", and "GHz" can also be
   used (for example "900MHz"). The following special values are
   supported: "min" - minimum CPU frequency supported by the OS (via
   Linux sysfs files), "hfm", "base", "P1" - base CPU frequency, "max" -
   maximum CPU frequency supported by the OS (via Linux sysfs), "eff",
   "lfm", "Pn" - maximum CPU efficiency frequency. This option has CPU
   scope.

**--max-freq**
   Get max. CPU frequency. Maximum CPU frequency is the highest
   frequency the operating system configured the CPU to run at (via
   sysfs knobs). The default unit is "Hz", but "kHz", "MHz", and "GHz"
   can also be used (for example "900MHz"). The following special values
   are supported: "min" - minimum CPU frequency supported by the OS (via
   Linux sysfs files), "hfm", "base", "P1" - base CPU frequency, "max" -
   maximum CPU frequency supported by the OS (via Linux sysfs), "eff",
   "lfm", "Pn" - maximum CPU efficiency frequency. This option has CPU
   scope.

**--min-freq-limit**
   Get min. supported CPU frequency. Minimum supported CPU frequency is
   the lowest frequency supported by the operating system (reported via
   sysfs knobs). This option has CPU scope.

**--max-freq-limit**
   Get max. supported CPU frequency. Maximum supported CPU frequency is
   the maximum CPU frequency supported by the operating system (reported
   via sysfs knobs). This option has CPU scope.

**--base-freq**
   Get base CPU frequency. Base CPU frequency is the highest sustainable
   CPU frequency. This frequency is also referred to as "guaranteed
   frequency", HFM (High Frequency Mode), or P1. The base frequency is
   acquired from a sysfs file of from an MSR register, if the sysfs file
   does not exist. This option has CPU scope.

**--min-freq-hw**
   Get min. CPU frequency (OS bypass). Minimum frequency the CPU is
   configured by the OS to run at. This value is read directly from the
   MSR(s), bypassing the OS. This option has CPU scope.

**--max-freq-hw**
   Get max. CPU frequency (OS bypass). Maximum frequency the CPU is
   configured by the OS to run at. This value is read directly from the
   MSR(s), bypassing the OS. This option has CPU scope.

**--min-oper-freq**
   Get min. CPU operating frequency. Minimum operating frequency is the
   lowest possible frequency the CPU can operate at. Depending on the
   CPU model, this frequency may or may not be directly available to the
   operating system, but the platform may use it in certain situations
   (e.g., in some C-states). This frequency is also referred to as Pm.
   Min. operating frequency is acquired from an MSR register, bypassing
   the OS. This option has CPU scope.

**--max-eff-freq**
   Get max. CPU efficiency frequency. Maximum efficiency frequency is
   the most energy efficient CPU frequency. This frequency is also
   referred to as LFM (Low Frequency Mode) or Pn. Max. efficiency
   frequency is acquired from an MSR register, bypassing the OS. This
   option has CPU scope.

**--turbo**
   Get current setting for turbo. When turbo is enabled, the CPUs can
   automatically run at a frequency greater than base frequency. Turbo
   on/off status is acquired and modified via sysfs knobs. This option
   has global scope.

**--max-turbo-freq**
   Get max. CPU turbo frequency. Maximum 1-core turbo frequency is the
   highest frequency a single CPU can operate at. This frequency is also
   referred to as max. 1-core turbo and P01. It is acquired from an MSR
   register, bypassing the OS. This option has CPU scope.

**--min-uncore-freq**
   Get min. uncore frequency. Minimum uncore frequency is the lowest
   frequency the operating system configured the uncore to run at. The
   default unit is "Hz", but "kHz", "MHz", and "GHz" can also be used
   (for example "900MHz"). The following special values are supported:
   "min" - minimum uncore frequency supported by the OS (via Linux sysfs
   files), "max" - maximum uncore frequency supported by the OS (via
   Linux sysfs). This option has die scope.

**--max-uncore-freq**
   Get max. uncore frequency. Maximum uncore frequency is the highest
   frequency the operating system configured the uncore to run at. The
   default unit is "Hz", but "kHz", "MHz", and "GHz" can also be used
   (for example "900MHz"). The following special values are supported:
   "min" - minimum uncore frequency supported by the OS (via Linux sysfs
   files), "max" - maximum uncore frequency supported by the OS (via
   Linux sysfs). This option has die scope.

**--min-uncore-freq-limit**
   Get min. supported uncore frequency. Minimum supported uncore
   frequency is the lowest uncore frequency supported by the operating
   system. This option has die scope.

**--max-uncore-freq-limit**
   Get max. supported uncore frequency. Maximum supported uncore
   frequency is the highest uncore frequency supported by the operating
   system. This option has die scope.

**--hwp**
   Get current setting for hardware power management. When hardware
   power management is enabled, CPUs can automatically scale their
   frequency without active OS involvement. This option has global
   scope.

**--epp**
   Get EPP (via sysfs). Energy Performance Preference is a hint to the
   CPU on energy efficiency vs performance. EPP value is a number in
   range of 0-255 (maximum energy efficiency to maximum performance), or
   a policy name. The value is read from or written to the
   'energy_performance_preference' Linux sysfs file. This option has CPU
   scope.

**--epp-hw**
   Get EPP (via MSR 0x774). Energy Performance Preference is a hint to
   the CPU on energy efficiency vs performance. EPP value is a number in
   range of 0-255 (maximum energy efficiency to maximum performance).
   When package control is enabled the value is read from MSR 0x772, but
   when written package control is disabled and value is written to MSR
   0x774, both require the 'msr' Linux kernel driver. This option has
   CPU scope.

**--epb**
   Get EPB (via sysfs). Energy Performance Bias is a hint to the CPU on
   energy efficiency vs performance. EBP value is a number in range of
   0-15 (maximum performance to maximum energy efficiency), or a policy
   name. The value is read from or written to the 'energy_perf_bias'
   Linux sysfs file. This option has CPU scope.

**--epb-hw**
   Get EPB (via MSR 0x1b0). Energy Performance Bias is a hint to the CPU
   on energy efficiency vs performance. EBP value is a number in range
   of 0-15 (maximum performance to maximum energy efficiency). The value
   is read from or written to MSR 0x1b0, which requires the 'msr' Linux
   kernel driver. This option has CPU scope.

**--driver**
   Get CPU frequency driver. CPU frequency driver enumerates and
   requests the P-states available on the platform. This option has
   global scope.

**--intel-pstate-mode**
   Get operation mode of 'intel_pstate' driver. The 'intel_pstate'
   driver has 3 operation modes: 'active', 'passive' and 'off'. The main
   difference between the active and passive mode is in what frequency
   governors are used - the generic Linux governors (passive mode) or
   the custom, built-in 'intel_pstate' driver governors (active mode).
   This option has global scope.

**--governor**
   Get CPU frequency governor. CPU frequency governor decides which
   P-state to select on a CPU depending on CPU business and other
   factors. This option has CPU scope.

COMMAND *'pepc* pstates config'
===============================

usage: pepc pstates config [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--core-siblings CORE_SIBLINGS] [--min-freq
[MIN_FREQ]] [--max-freq [MAX_FREQ]] [--min-freq-hw [MIN_FREQ_HW]]
[--max-freq-hw [MAX_FREQ_HW]] [--turbo [TURBO]] [--min-uncore-freq
[MIN_UNCORE_FREQ]] [--max-uncore-freq [MAX_UNCORE_FREQ]] [--epp [EPP]]
[--epp-hw [EPP_HW]] [--epb [EPB]] [--epb-hw [EPB_HW]]
[--intel-pstate-mode [INTEL_PSTATE_MODE]] [--governor [GOVERNOR]]

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

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to configure P-States on. The list can
   include individual core sibling indices or index ranges. For example,
   core x includes CPUs 3 and 4, '0' would mean CPU 3 and '1' would mean
   CPU 4. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the
   previous example if CPU 3 was offline, then '0' would mean CPU 4.

**--min-freq** *[MIN_FREQ]*
   Set min. CPU frequency. Minimum CPU frequency is the lowest frequency
   the operating system configured the CPU to run at (via sysfs knobs).
   The default unit is "Hz", but "kHz", "MHz", and "GHz" can also be
   used (for example "900MHz"). The following special values are
   supported: "min" - minimum CPU frequency supported by the OS (via
   Linux sysfs files), "hfm", "base", "P1" - base CPU frequency, "max" -
   maximum CPU frequency supported by the OS (via Linux sysfs), "eff",
   "lfm", "Pn" - maximum CPU efficiency frequency. This option has CPU
   scope.

**--max-freq** *[MAX_FREQ]*
   Set max. CPU frequency. Maximum CPU frequency is the highest
   frequency the operating system configured the CPU to run at (via
   sysfs knobs). The default unit is "Hz", but "kHz", "MHz", and "GHz"
   can also be used (for example "900MHz"). The following special values
   are supported: "min" - minimum CPU frequency supported by the OS (via
   Linux sysfs files), "hfm", "base", "P1" - base CPU frequency, "max" -
   maximum CPU frequency supported by the OS (via Linux sysfs), "eff",
   "lfm", "Pn" - maximum CPU efficiency frequency. This option has CPU
   scope.

**--min-freq-hw** *[MIN_FREQ_HW]*
   Set min. CPU frequency (OS bypass). Minimum frequency the CPU is
   configured by the OS to run at. This value is read directly from the
   MSR(s), bypassing the OS. This option has CPU scope.

**--max-freq-hw** *[MAX_FREQ_HW]*
   Set max. CPU frequency (OS bypass). Maximum frequency the CPU is
   configured by the OS to run at. This value is read directly from the
   MSR(s), bypassing the OS. This option has CPU scope.

**--turbo** *[TURBO]*
   Enable or disable turbo. When turbo is enabled, the CPUs can
   automatically run at a frequency greater than base frequency. Turbo
   on/off status is acquired and modified via sysfs knobs. Use "on" or
   "off". This option has global scope.

**--min-uncore-freq** *[MIN_UNCORE_FREQ]*
   Set min. uncore frequency. Minimum uncore frequency is the lowest
   frequency the operating system configured the uncore to run at. The
   default unit is "Hz", but "kHz", "MHz", and "GHz" can also be used
   (for example "900MHz"). The following special values are supported:
   "min" - minimum uncore frequency supported by the OS (via Linux sysfs
   files), "max" - maximum uncore frequency supported by the OS (via
   Linux sysfs). This option has die scope.

**--max-uncore-freq** *[MAX_UNCORE_FREQ]*
   Set max. uncore frequency. Maximum uncore frequency is the highest
   frequency the operating system configured the uncore to run at. The
   default unit is "Hz", but "kHz", "MHz", and "GHz" can also be used
   (for example "900MHz"). The following special values are supported:
   "min" - minimum uncore frequency supported by the OS (via Linux sysfs
   files), "max" - maximum uncore frequency supported by the OS (via
   Linux sysfs). This option has die scope.

**--epp** *[EPP]*
   Set EPP (via sysfs). Energy Performance Preference is a hint to the
   CPU on energy efficiency vs performance. EPP value is a number in
   range of 0-255 (maximum energy efficiency to maximum performance), or
   a policy name. The value is read from or written to the
   'energy_performance_preference' Linux sysfs file. This option has CPU
   scope.

**--epp-hw** *[EPP_HW]*
   Set EPP (via MSR 0x774). Energy Performance Preference is a hint to
   the CPU on energy efficiency vs performance. EPP value is a number in
   range of 0-255 (maximum energy efficiency to maximum performance).
   When package control is enabled the value is read from MSR 0x772, but
   when written package control is disabled and value is written to MSR
   0x774, both require the 'msr' Linux kernel driver. This option has
   CPU scope.

**--epb** *[EPB]*
   Set EPB (via sysfs). Energy Performance Bias is a hint to the CPU on
   energy efficiency vs performance. EBP value is a number in range of
   0-15 (maximum performance to maximum energy efficiency), or a policy
   name. The value is read from or written to the 'energy_perf_bias'
   Linux sysfs file. This option has CPU scope.

**--epb-hw** *[EPB_HW]*
   Set EPB (via MSR 0x1b0). Energy Performance Bias is a hint to the CPU
   on energy efficiency vs performance. EBP value is a number in range
   of 0-15 (maximum performance to maximum energy efficiency). The value
   is read from or written to MSR 0x1b0, which requires the 'msr' Linux
   kernel driver. This option has CPU scope.

**--intel-pstate-mode** *[INTEL_PSTATE_MODE]*
   Set operation mode of 'intel_pstate' driver. The 'intel_pstate'
   driver has 3 operation modes: 'active', 'passive' and 'off'. The main
   difference between the active and passive mode is in what frequency
   governors are used - the generic Linux governors (passive mode) or
   the custom, built-in 'intel_pstate' driver governors (active mode).
   This option has global scope.

**--governor** *[GOVERNOR]*
   Set CPU frequency governor. CPU frequency governor decides which
   P-state to select on a CPU depending on CPU business and other
   factors. This option has CPU scope.

COMMAND *'pepc* pstates save'
=============================

usage: pepc pstates save [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--core-siblings CORE_SIBLINGS] [-o OUTFILE]

Save all the modifiable P-state settings into a file. This file can
later be used for restoring P-state settings with the 'pepc pstates
restore' command.

OPTIONS *'pepc* pstates save'
=============================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to save P-state information about. The list can include
   individual CPU numbers and CPU number ranges. For example,
   '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use
   the special keyword 'all' to specify all CPUs. If the
   CPUs/cores/packages were not specified, all CPUs will be used as the
   default value.

**--cores** *CORES*
   List of cores to save P-state information about. The list can include
   individual core numbers and core number ranges. For example,
   '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to save P-state information about. The list can
   include individual package numbers and package number ranges. For
   example, '1-3' would mean packages 1 to 3, and '1,3' would mean
   packages 1 and 3. Use the special keyword

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to save P-state information about. The
   list can include individual core sibling indices or index ranges. For
   example, core x includes CPUs 3 and 4, '0' would mean CPU 3 and '1'
   would mean CPU 4. This option can only be used to reference online
   CPUs, because Linux does not provide topology information for offline
   CPUs. In the previous example if CPU 3 was offline, then '0' would
   mean CPU 4.

**-o** *OUTFILE*, **--outfile** *OUTFILE*
   Name of the file to save the settings to (printed to standard output
   by default).

COMMAND *'pepc* pstates restore'
================================

usage: pepc pstates restore [-h] [-q] [-d] [-f INFILE]

Restore P-state settings from a file previously created with the 'pepc
pstates save' command.

OPTIONS *'pepc* pstates restore'
================================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**-f** *INFILE*, **--from** *INFILE*
   Name of the file restore the settings from (use "-" to read from the
   standard output.

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

COMMAND *'pepc* topology'
=========================

usage: pepc topology [-h] [-q] [-d] {info} ...

Various commands related to CPU topology.

OPTIONS *'pepc* topology'
=========================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

FURTHER SUB-COMMANDS *'pepc topology'*
======================================

**pepc topology** *info*
   Print CPU topology.

COMMAND *'pepc* topology info'
==============================

usage: pepc topology info [-h] [-q] [-d] [--cpus CPUS] [--cores CORES]
[--packages PACKAGES] [--core-siblings CORE_SIBLINGS] [--order ORDER]
[--online-only] [--columns COLUMNS]

Print CPU topology information. Note, the topology information for some
offline CPUs may be unavailable, in these cases the number will be
substituted with "?".

OPTIONS *'pepc* topology info'
==============================

**-h**
   Show this help message and exit.

**-q**
   Be quiet.

**-d**
   Print debugging information.

**--cpus** *CPUS*
   List of CPUs to print topology information for. The list can include
   individual CPU numbers and CPU number ranges. For example,
   '1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use
   the special keyword 'all' to specify all CPUs. If the
   CPUs/cores/packages were not specified, all CPUs will be used as the
   default value.

**--cores** *CORES*
   List of cores to print topology information for. The list can include
   individual core numbers and core number ranges. For example,
   '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all cores.

**--packages** *PACKAGES*
   List of packages to print topology information for. The list can
   include individual package numbers and package number ranges. For
   example, '1-3' would mean packages 1 to 3, and '1,3' would mean
   packages 1 and 3. Use the special keyword

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to print topology information for. The
   list can include individual core sibling indices or index ranges. For
   example, core x includes CPUs 3 and 4, '0' would mean CPU 3 and '1'
   would mean CPU 4. This option can only be used to reference online
   CPUs, because Linux does not provide topology information for offline
   CPUs. In the previous example if CPU 3 was offline, then '0' would
   mean CPU 4.

**--order** *ORDER*
   By default, the topology table is printed in CPU number order. Use
   this option to print it in a different order (e.g., core or package
   number order). Here are the supported order names: cpu, core, module,
   die, node, package.

**--online-only**
   Include only online CPUs. By default offline and online CPUs are
   included.

**--columns** *COLUMNS*
   By default, the topology columns are CPU, core, module, die, node,
   package, "die" and "module" columns are not printed if there is only
   one die per package and no modules. Use this option to select
   topology columns names and order (e.g.

AUTHORS
=======

::

   Artem Bityutskiy

::

   dedekind1@gmail.com

DISTRIBUTION
============

The latest version of pepc may be downloaded from
` <https://github.com/intel/pepc>`__
