.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: P-states

.. Contents::
   :depth: 2
..

===================
Command *'pstates'*
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
   User name for SSH login to the remote host. Defaults to 'root.

**-U** *USERNAME*, **--username** *USERNAME*
   Name of the user to use for logging into the remote host over SSH. The default user name is
   'root'.

**-K** *PRIVKEY*, **--priv-key** *PRIVKEY*
   Path to the private SSH key for logging into the remote host. Defaults to keys in standard paths
   like '$HOME/.ssh'.

**-T** *TIMEOUT*, **--timeout** *TIMEOUT*
   Timeout for establishing an SSH connection in seconds. Defaults to 8.

**-D** *DATASET*, **--dataset** *DATASET*
   This option is for debugging and testing. It specifies the dataset to emulate a host for running
   the command. Typically used when running 'pepc' from the source directory, which includes datasets
   for various systems.

   The argument can be a dataset path or name. If specified by name, the following locations are
   searched for the dataset.

   1. './tests/data' in the program's directory
   2. '$PEPC_DATA_PATH/tests/data'
   3. '$HOME/.local/share/pepc/tests/data'
   4. '/usr/local/share/pepc/tests/data'
   5. '/usr/share/pepc/tests/data'

**--force-color**
   Force colorized output even if the output stream is not a terminal (adds ANSI escape codes).

**--override-cpu-model** *VFM*
   This option is for debugging and testing purposes only. Override the target host CPU model and
   force {TOOLNAME} treat the host as a specific CPU model. The format is
   '[<Vendor>:][<Family>:]<Model>', where '<Vendor>' is the CPU vendor (e.g., 'GenuineIntel' or
   'AuthenticAMD'), '<Family>' is the CPU family (e.g., 6), and '<Model>' is the CPU model (e.g.,
   0x8F). Example: 'GenuineIntel:6:0x8F' will force the tool treating the target host CPU as a
   Sapphire Rapids Xeon. The vendor and family are optional and if not specified, the tool will use
   the vendor and family of the target host CPU. The family and model can be specified in decimal
   or hexadecimal format.

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

Get P-states information for specified CPUs. By default, print all information about all CPUs.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**--yaml**
   Print information in YAML format.

**--list-mechanisms**
   List mechanisms available for reading P-states information.

**--min-freq**
   Get minimum CPU frequency (details in 'min_freq_').

**--max-freq**
   Get maximum CPU frequency (details in 'max_freq_').

**--min-freq-limit**
   Get minimum supported CPU frequency (details in 'min_freq_limit_').

**--max-freq-limit**
   Get maximum supported CPU frequency (details in 'max_freq_limit_').

**--frequencies**
   Get acceptable CPU frequencies (details in 'frequencies_').

**--base-freq**
   Get base CPU frequency (details in 'base_freq_').

**--bus-clock**
   Get bus clock speed (details in 'bus_clock_').

**--min-oper-freq**
   Get minimum CPU operating frequency (details in 'min_oper_freq_').

**--max-eff-freq**
   Get maximum CPU efficiency frequency (details in 'max_eff_freq_').

**--turbo**
   Check if turbo is enabled or disabled (details in 'turbo_').

**--max-turbo-freq**
   Get maximum CPU turbo frequency (details in 'max_turbo_freq_').

**--min-uncore-freq**
   Get minimum uncore frequency (details in 'min_uncore_freq_').

**--max-uncore-freq**
   Get maximum uncore frequency (details in 'max_uncore_freq_').

**--min-uncore-freq-limit**
   Get minimum supported uncore frequency (details in 'min_uncore_freq_limit_').

**--max-uncore-freq-limit**
   Get maximum supported uncore frequency (details in 'max_uncore_freq_limit_').

**--hwp**
   Check if hardware power management is enabled or disabled (details in 'hwp_').

**--epp**
   Get EPP via sysfs (details in 'epp_').

**--epb**
   Get EPB via sysfs (details in 'epb_').

**--driver**
   Get CPU frequency driver (details in 'driver_').

**--intel-pstate-mode**
   Get operation mode of 'intel_pstate' driver (details in 'intel_pstate_mode_').

**--governor**
   Get CPU frequency governor (details in 'governor_').

**--governors**
   Get list of available CPU frequency governors (details in 'governors_').

Subcommand *'config'*
=====================

Configure P-states on specified CPUs. All options can be used without a parameter, in which case the
currently configured value(s) will be printed.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
    Comma-separated list of mechanisms that are allowed to be used for configuring P-states. Use
    '--list-mechanisms' to get the list of available mechanisms. Note, many options support only one
    mechanism (e.g., 'sysfs'), some may support multiple (e.g., 'sysfs' and 'msr'). The mechanisms
    are tried in the specified order. By default, all mechanisms are allowed and the most
    preferred mechanisms will be tried first.

**--list-mechanisms**
   List mechanisms available for configuring P-states.

**--min-freq** *MIN_FREQ*
   Set minimum CPU frequency (details in 'min_freq_').

**--max-freq** *MAX_FREQ*
   Set maximum CPU frequency (details in 'max_freq_').

**--turbo** *on|off*
   Enable or disable turbo (details in 'turbo_').

**--min-uncore-freq** *MIN_UNCORE_FREQ*
   Set minimum uncore frequency (details in 'min_uncore_freq_').

**--max-uncore-freq** *MAX_UNCORE_FREQ*
   Set maximum uncore frequency (details in 'max_uncore_freq_').

**--epp** *EPP*
   Set EPP via sysfs (details in 'epp_').

**--epb** *EPB*
   Set EPB via sysfs (details in 'epb_').

**--intel-pstate-mode** *[MODE]*
   Set operation mode of 'intel_pstate' driver (details in 'intel_pstate_mode_').

**--governor** *[NAME]*
   Set CPU frequency governor (details in 'governor_').

Subcommand *'save'*
===================

Save all the modifiable P-state settings into a file. This file can later be used for restoring
P-state settings with the 'pepc pstates restore' command.

Use target CPU specification options to specify the subset of CPUs, cores, dies, or packages.

**-o** *OUTFILE*, **--outfile** *OUTFILE*
   Name of the file to save the settings to (printed to standard output
   by default).

Subcommand *'restore'*
======================

Restore P-state settings from a file previously created with the 'pepc pstates save' command.

**-f** *INFILE*, **--from** *INFILE*
   Name of the file from which to restore the settings from, use "-" to read from the standard
   output.

----------------------------------------------------------------------------------------------------

==========
Properties
==========

min_freq
========

min_freq - Minimum CPU frequency

Synopsis
--------

| pepc pstates *info* **--min-freq**
| pepc pstates *config* **--min-freq**\ =<value>

Description
-----------

Minimum CPU frequency is the lowest frequency the CPU was configured the CPU to run at.

The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also be used
(for example "900MHz").

The following special values are supported:

**min**
   Minimum frequency supported by the Linux CPU frequency driver (see 'min_freq_limit_').
**max**
   Maximum frequency supported by the Linux CPU frequency driver (see 'max_freq_limit_').
**base**, **hfm**, **P1**
   Base CPU frequency (see 'base_freq_').
**eff**, **lfm**, **Pn**
   Maximum CPU efficiency frequency (see 'max_eff_freq_').
**Pm**
   Minimum CPU operating frequency (see 'min_oper_freq_').

Note, on some systems 'Pm' is lower than 'lfm'. For example, 'Pm' may be 500MHz,
while 'lfm' may be 800MHz. On those system, Linux may be using 'lfm' as the minimum
supported frequency limit. So from Linux perspective, the minimum frequency may be 800MHz, not
500MHz. In this case '--min-freq 500MHz --mechanisms sysfs' will fail, while
'--min-freq 500MHz --mechanisms sysfs' will succeed. And '--min-freq 500MHz' will also
succeed, because by default, pepc tries all the available mechanisms.

Mechanisms
----------

**sysfs**
"/sys/devices/system/cpu/policy0/scaling_min_freq", where '0' is replaced with desired CPU
number.

**msr**
MSR_HWP_REQUEST (0x774), bits 7:0.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

max_freq
========

max_freq - Maximum CPU frequency

Synopsis
--------

| pepc pstates *info* **--max-freq**
| pepc pstates *config* **--max-freq**\ =<value>

Description
-----------

Maximum CPU frequency is the highest frequency the CPU was configured to run at.

The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also be used (for example '900MHz').

The following special values are supported:

**min**
   Minimum frequency supported by the Linux CPU frequency driver (see 'min_freq_limit_').
**max**
   Maximum frequency supported by the Linux CPU frequency driver (see 'max_freq_limit_').
**base**, **hfm**, **P1**
   Base CPU frequency (see 'base_freq_').
**eff**, **lfm**, **Pn**
   Maximum CPU efficiency frequency (see 'max_eff_freq_').
**Pm**
   Minimum CPU operating frequency (see 'min_oper_freq_').

Mechanisms
----------

**sysfs**
"/sys/devices/system/cpu/policy0/scaling_max_freq", where '0' is replaced with desired CPU
number.

**msr**
MSR_HWP_REQUEST (0x774), bits 15:8.

-----

This property has CPU scope.

min_freq_limit
==============

min_freq_limit - Minimum supported CPU frequency

Synopsis
--------

pepc pstates *info* **--min-freq-limit**

Description
-----------

Minimum supported CPU frequency is the lowest frequency the CPU can be configured to run at.

Mechanism
---------

**sysfs**
"/sys/devices/system/cpu/policy0/cpuinfo_min_freq", where '0' is replaced with desired CPU
number.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

max_freq_limit
==============

max_freq_limit - Maximum supported CPU frequency

Synopsis
--------

pepc pstates *info* **--min-freq-limit**

Description
-----------

Maximum supported CPU frequency is the highest frequency the CPU can be configured to run at.

Mechanism
---------

**sysfs**
"/sys/devices/system/cpu/policy0/cpuinfo_max_freq", where '0' is replaced with desired CPU
number.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

frequencies
===========

frequencies - acceptable CPU frequencies

Synopsis
--------

| pepc pstates *info* **--frequencies**

Description
-----------

List of CPU frequencies exposed by the Linux CPU frequency driver and available for the users via
'--min-freq' and '--max-freq' options.

Mechanisms
----------

**sysfs**
"/sys/devices/system/cpu/cpufreq/policy0/scaling_available_frequencies", '0' is replaced
with desired CPU number.

**doc**
In case of Intel CPUs and 'intel_idle' driver, assume all frequencies from 'min_freq_limit_' to
'max_freq_limit_' with 'bus_clock_' step.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

base_freq
=========

base_freq - Base CPU frequency

Synopsis
--------

pepc pstates *info* **--base-freq**

Description
-----------

Base CPU frequency is the highest sustainable CPU frequency. This frequency is also referred to as
"guaranteed frequency", HFM (High Frequency Mode), or P1.

The base frequency is acquired from a sysfs file or from an MSR register, depending on platform and
the CPU frequency driver.

Mechanisms
----------

**sysfs**
"/sys/devices/system/cpu/policy0/base_frequency", where '0' is replaced with desired CPU
number. If this file does not exist, the "/sys/devices/system/cpu/cpu0/cpufreq/bios_limit"
sysfs file is used (where '0' is replaced with desired CPU number).

**msr**
MSR_PLATFORM_INFO (0xCE), bits 15:8.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

bus_clock
=========

bus_clock - Bus clock speed.

Synopsis
--------

pepc pstates *info* **--bus-clock**

Description
-----------

Bus clock refers to how quickly the system bus can move data from one computer component to the
other.

Mechanisms
----------

**msr**
MSR_FSB_FREQ (0xCD), bits 2:0.
**doc**
100MHz on modern Intel platforms.

Scope
-----

This property has package scope. Exceptions: Silvermonts and Airmonts have module scope.

----------------------------------------------------------------------------------------------------

min_oper_freq
=============

min_oper_freq - Minimum CPU operating frequency

Synopsis
--------

pepc pstates *info* **--min-oper-freq**

Description
-----------

Minimum operating frequency is the lowest possible frequency the CPU can operate at. Depending on
the CPU model, this frequency may or may not be directly available to the OS, but the
platform may use it in certain situations (e.g., in some C-states). This frequency is also referred
to as Pm.

Mechanism
---------

**msr**
MSR_PLATFORM_INFO (0xCE), bits 55:48.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

max_eff_freq
============

max_eff_freq - Maximum CPU efficiency frequency

Synopsis
--------

pepc pstates *info* **--max-eff-freq**

Description
-----------

Maximum efficiency frequency is the most energy efficient CPU frequency. This frequency is also
referred to as LFM (Low Frequency Mode) or Pn.

Mechanism
---------

**msr**
MSR_PLATFORM_INFO (0xCE), bits 47:40.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

turbo
=====

turbo - Turbo

Synopsis
--------

| pepc pstates *info* **--turbo**
| pepc pstates *config* **--turbo**\ =<on|off>

Description
-----------

When turbo is enabled, the CPUs can automatically run at a frequency greater than base frequency.

Mechanism
---------

**sysfs**
Location of the turbo knob in sysfs depends on the CPU frequency driver.

intel_pstate - "/sys/devices/system/cpu/intel_pstate/no_turbo"

acpi-cpufreq - "/sys/devices/system/cpu/cpufreq/boost"

Scope
-----

This property has global scope.

----------------------------------------------------------------------------------------------------

max_turbo_freq
==============

max_turbo_freq - Maximum CPU turbo frequency

Synopsis
--------

| pepc pstates *info* **--max-turbo-freq**

Description
-----------

Maximum 1-core turbo frequency is the highest frequency a single CPU can operate at. This frequency
is also referred to as max. 1-core turbo and P01.

Mechanism
---------

**msr**
MSR_TURBO_RATIO_LIMIT (0x1AD), bits 7:0.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

min_uncore_freq
===============

min_uncore_freq - Minimum uncore frequency

Synopsis
--------

| pepc pstates *info* **--min-uncore-freq**
| pepc pstates *config* **--min-uncore-freq**\ =<value>

Description
-----------

Minimum uncore frequency is the lowest frequency the OS configured the CPU to run at, via sysfs knobs.

The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also be used
(for example '900MHz').

The following special values are supported:

**min**
   Minimum uncore frequency supported (see 'min_freq_limit_').
**max**
   Maximum uncore frequency supported (see 'max_freq_limit_').
**mdl**
   Middle uncore frequency between minimum and maximum rounded to nearest 100MHz.

Mechanism
---------

**sysfs**

In case of 'intel_uncore_frequency_tpmi' driver, file
"/sys/devices/system/cpu/intel_uncore_frequency/uncore00/min_freq_khz",
where '00' is replaced with the uncore number corresponding to the desired package
and die numbers.

In case of 'intel_uncore_frequency' driver, file
"/sys/devices/system/cpu/intel_uncore_frequency/package_00_die_01/min_freq_khz",
where '00' is replaced with desired package number and '01' is replaced with desired die number.

Scope
-----

This property has die scope.

----------------------------------------------------------------------------------------------------

max_uncore_freq
===============

max_uncore_freq - Maximum uncore frequency

Synopsis
--------

| pepc pstates *info* **--max-uncore-freq**
| pepc pstates *config* **--max-uncore-freq**\ =<value>

Description
-----------

Maximum uncore frequency is the highest frequency the OS configured the CPU to run at, via sysfs knobs.

The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also be used
(for example "900MHz").

The following special values are supported:

**min**
   Minimum uncore frequency supported (see 'min_freq_limit_').
**max**
   Maximum uncore frequency supported (see 'max_freq_limit_').
**mdl**
   Middle uncore frequency between minimum and maximum rounded to nearest 100MHz.

Mechanism
---------

**sysfs**

In case of 'intel_uncore_frequency_tpmi' driver, file
"/sys/devices/system/cpu/intel_uncore_frequency/uncore00/max_freq_khz",
where '00' is replaced with the uncore number corresponding to the desired package
and die numbers.

In case of 'intel_uncore_frequency' driver, file
"/sys/devices/system/cpu/intel_uncore_frequency/package_00_die_01/max_freq_khz",
where '00' is replaced with desired package number and '01' is replaced with desired die number.

Scope
-----

This property has die scope.

----------------------------------------------------------------------------------------------------

min_uncore_freq_limit
=====================

min_uncore_freq_limit - Minimum supported uncore frequency

Synopsis
--------

pepc pstates *info* **--min-uncore-freq-limit**

Description
-----------

Minimum supported uncore frequency is the lowest uncore frequency supported by the OS.

Mechanism
---------

**sysfs**

In case of 'intel_uncore_frequency_tpmi' driver, file
"/sys/devices/system/cpu/intel_uncore_frequency/uncore00/initial_min_freq_khz",
where '00' is replaced with the uncore number corresponding to the desired package
and die numbers.

"/sys/devices/system/cpu/intel_uncore_frequency/package_00_die_01/initial_min_freq_khz",
where '00' is replaced with desired package number and '01' is replaced with desired
die number.

Scope
-----

This property has die scope.

----------------------------------------------------------------------------------------------------

max_uncore_freq_limit
=====================

max_uncore_freq_limit - Maximum supported uncore frequency

Synopsis
--------

pepc pstates *info* **--max-uncore-freq-limit**

Description
-----------

Maximum supported uncore frequency is the highest uncore frequency supported by the OS.

Mechanism
---------

**sysfs**

In case of 'intel_uncore_frequency_tpmi' driver, file
"/sys/devices/system/cpu/intel_uncore_frequency/uncore00/initial_max_freq_khz",
where '00' is replaced with the uncore number corresponding to the desired package
and die numbers.

"/sys/devices/system/cpu/intel_uncore_frequency/package_00_die_01/initial_max_freq_khz",
where '00' is replaced with desired package number and '01' with desired
die number.

Scope
-----

This property has die scope.

----------------------------------------------------------------------------------------------------

hwp
===

hwp - Hardware power management

Synopsis
--------

pepc pstates *info* **--hwp**

Description
-----------

When hardware power management is enabled, CPUs can automatically scale their frequency without
active OS involvement.

Mechanism
---------

**msr**
MSR_PM_ENABLE (0x770), bit 0.

Scope
-----

This property has global scope.

----------------------------------------------------------------------------------------------------

epp
===

epp - Energy Performance Preference

Synopsis
--------

| pepc pstates *info* **--epp**
| pepc pstates *config* **--epp**\ =<value>

Description
-----------

Energy Performance Preference is a hint to the CPU on energy efficiency vs performance. EPP value is
a number in range of 0-255 (maximum energy efficiency to maximum performance), or a policy name.

Mechanisms
---------

**sysfs**
"/sys/devices/system/cpu/cpufreq/policy0/energy_performance_preference", where '0' is replaced
with desired CPU number.

**msr**
MSR_HWP_REQUEST (0x774), bits 31:24.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

epb
===
epb - Energy Performance Bias

Synopsis
--------

| pepc pstates *info* **--epb**
| pepc pstates *config* **--epb**\ =<value>

Description
-----------

Energy Performance Bias is a hint to the CPU on energy efficiency vs performance. EBP value is a
number in range of 0-15 (maximum performance to maximum energy efficiency), or a policy name.

Mechanisms
----------

**sysfs**
"/sys/devices/system/cpu/cpu0/power/energy_perf_bias", where '0' is replaced with desired CPU
number.

**msr**
MSR_ENERGY_PERF_BIAS (0x1B0), bits 3:0.

Scope
-----

This property has CPU scope on most platforms. However, on Silvermont systems it has core
scope and on Westmere and Sandybridge systems it has package scope.

----------------------------------------------------------------------------------------------------

driver
======

driver - CPU frequency driver

Synopsis
--------

pepc pstates *info* **--driver**

Description
-----------

CPU frequency driver enumerates and requests the P-states available on the platform.

Mechanism
---------

**sysfs**
"/sys/devices/system/cpu/cpufreq/policy0/scaling_driver", where '0' is replaced with desired
CPU number.

Scope
-----

This property has global scope.

----------------------------------------------------------------------------------------------------

intel_pstate_mode
=================

intel_pstate_mode - Operation mode of 'intel_pstate' driver

Synopsis
--------

| pepc pstates *info* **--intel-pstate-mode**
| pepc pstates *config* **--intel-pstate-mode**\ =<mode>

Description
-----------

The 'intel_pstate' driver has 3 operation modes: 'active', 'passive' and 'off'. The main
difference between the active and passive mode is in which frequency governors are used - the
generic Linux governors (passive mode) or the custom, built-in 'intel_pstate' driver governors
(active mode).

Mechanism
---------

**sysfs**
"/sys/devices/system/cpu/intel_pstate/status".

Scope
-----

This property has global scope.

----------------------------------------------------------------------------------------------------

governor
========

governor - CPU frequency governor

Synopsis
--------

| pepc pstates *info* **--governor**
| pepc pstates *config* **--governor**\ =<name>

Description
-----------

CPU frequency governor decides which P-state to select on a CPU depending on CPU business and other
factors.

Mechanism
---------

**sysfs**
"/sys/devices/system/cpu/cpufreq/policy0/scaling_governor", where '0' is replaced with desired
CPU number.

Scope
-----

This property has CPU scope.

----------------------------------------------------------------------------------------------------

governors
=========

governors - Available CPU frequency governors

Synopsis
--------

pepc pstates *info* **--governors**

Description
-----------

CPU frequency governors decide which P-state to select on a CPU depending on CPU business and other
factors. Different governors implement different selection policy.

Mechanism
---------

**sysfs**
"/sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors", where '0' is replaced
with desired CPU number.

Scope
-----

This property has global scope.
