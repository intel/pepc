.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Date:   09-03-2023
:Title:  PSTATES

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

Get P-states information for specified CPUs. By default, prints all information for all CPUs.

**--cpus** *CPUS*
   List of CPUs to get information about. The list can include individual CPU numbers and CPU number
   ranges. For example,'1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the
   special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to get information about. The list can include individual core numbers and
   core number ranges. For example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to
   1. Use the special keyword 'all' to specify all cores. This option has to be accompanied by
   '--package' option, because core numbers are per-package.

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

**--base-freq**
   Get base CPU frequency (details in 'base_freq_').

**--min-freq-hw**
   Get minimum CPU frequency (OS bypass) (details in 'min_freq_hw_').

**--max-freq-hw**
   Get maximum CPU frequency (OS bypass) (details in 'max_freq_hw_').

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

**--epp-hw**
   Get EPP via MSR (details in 'epp_hw_').

**--epb**
   Get EPB via sysfs (details in 'epb_').

**--epb-hw**
   Get EPB via MSR (details in 'epb_hw_').

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

**--cpus** *CPUS*
   List of CPUs to configure P-States on. The list can include individual CPU numbers and CPU number
   ranges. For example,'1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12. Use the
   special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to configure P-States on. The list can include individual core numbers and
   core number ranges. For example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to
   12. Use the special keyword 'all' to specify all cores. This option has to be accompanied by
   '--package' option, because core numbers are per-package.

**--packages** *PACKAGES*
   List of packages to configure P-States on. The list can include individual package numbers and
   package number ranges. For example, '0,2-4' would mean package 0 and packages 2 to 4. Use the
   special keyword 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to configure P-States on. The list can include individual core
   sibling indices or index ranges. For example, core x includes CPUs 3 and 4, '0' would mean CPU 3
   and '1' would mean CPU 4. This option can only be used to reference online CPUs, because Linux
   does not provide topology information for offline CPUs. In the previous example if CPU 3 was
   offline, then '0' would mean CPU 4.

**--override-cpu-model** *MODEL*
   This option is for debugging and testing purposes only. Provide the CPU model number which the
   tool treats the target system CPU as. For example, use 0x8F to treat the target system as
   Sapphire Rapids Xeon.

**--list-mechanisms**
   List mechanisms available for configuring P-states.

**--min-freq** *MIN_FREQ*
   Set minimum CPU frequency (details in 'min_freq_').

**--max-freq** *MAX_FREQ*
   Set maximum CPU frequency (details in 'max_freq_').

**--min-freq-hw** *MIN_FREQ*
   Set minimum CPU frequency (OS bypass) (details in 'min_freq_limit_').

**--max-freq-hw** *MAX_FREQ*
   Set maximum CPU frequency (OS bypass) (details in 'max_freq_limit_').

**--turbo** *on|off*
   Enable or disable turbo (details in 'turbo_').

**--min-uncore-freq** *MIN_UNCORE_FREQ*
   Set minimum uncore frequency (details in 'min_uncore_freq_').

**--max-uncore-freq** *MAX_UNCORE_FREQ*
   Set maximum uncore frequency (details in 'max_uncore_freq_').

**--epp** *EPP*
   Set EPP via sysfs (details in 'epp_').

**--epp-hw** *EPP*
   Set EPP via MSR (details in 'epp_hw_').

**--epb** *EPB*
   Set EPB via sysfs (details in 'epb_').

**--epb-hw** *EPB*
   Set EPB via MSR (details in 'epb_hw_').

**--intel-pstate-mode** *[MODE]*
   Set operation mode of 'intel_pstate' driver (details in 'intel_pstate_mode_').

**--governor** *[NAME]*
   Set CPU frequency governor (details in 'governor_').

Subcommand *'save'*
===================

Save all the modifiable P-state settings into a file. This file can later be used for restoring
P-state settings with the 'pepc pstates restore' command.

**--cpus** *CPUS*
   List of CPUs to save P-state information about. The list can include individual CPU numbers and
   CPU number ranges. For example,'1-4,7,8,10-12' would mean CPUs 1 to 4, CPUs 7, 8, and 10 to 12.
   Use the special keyword 'all' to specify all CPUs.

**--cores** *CORES*
   List of cores to save P-state information about. The list can include individual core numbers and
   core number ranges. For example, '1-4,7,8,10-12' would mean cores 1 to 4, cores 7, 8, and 10 to
   12. Use the special keyword 'all' to specify all cores. This option has to be accompanied by
   '--package' option, because core numbers are per-package.

**--packages** *PACKAGES*
   List of packages to save P-state information about. The list can include individual package
   numbers and package number ranges. For example, '0,2-4' would mean package 0 and packages 2 to 4.
   Use the special keyword 'all' to specify all packages.

**--core-siblings** *CORE_SIBLINGS*
   List of core sibling indices to save P-state information about. The list can include individual
   core sibling indices or index ranges. For example, core x includes CPUs 3 and 4, '0' would mean
   CPU 3 and '1' would mean CPU 4. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the previous example if CPU 3
   was offline, then '0' would mean CPU 4.

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

The default unit is "**Hz**", but "**kHz**", "**MHz**", and "**GHz**" can also be used
(for example "900MHz").

The following special values are supported:

"**min**"
   Minimum supported CPU frequency (see 'min_freq_limit_').
"**max**"
   Maximum supported CPU frequency (see 'max_freq_limit_').
"**base**", "**hfm**", "**P1**"
   Base CPU frequency (see 'base_freq_').
"**eff**", "**lfm**", "**Pn**"
   Maximum CPU efficiency frequency (see 'max_eff_freq_').
"**Pm**"
   Minimum CPU operating frequency (see 'min_oper_freq_').

Mechanism
---------

"/sys/devices/system/cpu/policy\ **0**\ /scaling_min_freq", '**0**' is replaced with desired CPU
number.

Scope
-----

This property has **CPU** scope.

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

The default unit is "**Hz**", but "**kHz**", "**MHz**", and "**GHz**" can also be used
(for example "900MHz").

The following special values are supported:

"**min**"
   Minimum supported CPU frequency (see 'min_freq_limit_').
"**max**"
   Maximum supported CPU frequency (see 'max_freq_limit_').
"**base**", "**hfm**", "**P1**"
   Base CPU frequency (see 'base_freq_').
"**eff**", "**lfm**", "**Pn**"
   Maximum CPU efficiency frequency (see 'max_eff_freq_').
"**Pm**"
   Minimum CPU operating frequency (see 'min_oper_freq_').

Mechanism
---------

"/sys/devices/system/cpu/policy\ **0**\ /scaling_max_freq", '**0**' is replaced with desired CPU
number.

Scope
-----

This property has **CPU** scope.

----------------------------------------------------------------------------------------------------

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

"/sys/devices/system/cpu/policy\ **0**\ /cpuinfo_min_freq", '**0**' is replaced with desired CPU
number.

Scope
-----

This property has **CPU** scope.

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

"/sys/devices/system/cpu/policy\ **0**\ /cpuinfo_max_freq", '**0**' is replaced with desired CPU
number.

Scope
-----

This property has **CPU** scope.

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
"guaranteed frequency", **HFM** (High Frequency Mode), or **P1**.

The base frequency is acquired from a sysfs file or from an MSR register, depending on platform and
the CPU frequency driver.

Mechanism
---------

"/sys/devices/system/cpu/policy\ **0**\ /base_frequency", '**0**' is replaced with desired CPU
number. If the "base_frequency" file does not exist then either MSR_PLATFORM_INFO **(0xCE)**, bits
**15:8** is used (Intel platforms) or the "/sys/devices/system/cpu/cpu\ **0**\ /cpufreq/bios_limit"
sysfs file is used (non-Intel platforms, '**0**' is replaced with desired CPU number).

Scope
-----

This property has **CPU** scope.

----------------------------------------------------------------------------------------------------

min_freq_hw
===========

min_freq_hw - Minimum CPU frequency

Synopsis
--------

| pepc pstates *info* **--min-freq-hw**
| pepc pstates *config* **--min-freq-hw**\ =<value>

Description
-----------

Minimum CPU frequency is the lowest frequency the CPU was configured the CPU to run at.

The default unit is "**Hz**", but "**kHz**", "**MHz**", and "**GHz**" can also be used
(for example "900MHz").

The following special values are supported:

"**min**"
   Minimum supported CPU frequency (see 'min_freq_limit_').
"**max**"
   Maximum supported CPU frequency (see 'max_freq_limit_').
"**base**", "**hfm**", "**P1**"
   Base CPU frequency (see 'base_freq_').
"**eff**", "**lfm**", "**Pn**"
   Maximum CPU efficiency frequency (see 'max_eff_freq_').
"**Pm**"
   Minimum CPU operating frequency (see 'min_oper_freq_').

Mechanism
---------

MSR_HWP_REQUEST (**0x774**), bits **7:0**.

Scope
-----

This property has **CPU** scope.

----------------------------------------------------------------------------------------------------

max_freq_hw
===========

max_freq_hw - Maximum CPU frequency

Synopsis
--------

| pepc pstates *info* **--max-freq-hw**
| pepc pstates *config* **--max-freq-hw**\ =<value>

Description
-----------

Minimum CPU frequency is the lowest frequency the CPU was configured the CPU to run at.

The default unit is "**Hz**", but "**kHz**", "**MHz**", and "**GHz**" can also be used
(for example "900MHz").

The following special values are supported:

"**min**"
   Minimum supported CPU frequency (see 'min_freq_limit_').
"**max**"
   Maximum supported CPU frequency (see 'max_freq_limit_').
"**base**", "**hfm**", "**P1**"
   Base CPU frequency (see 'base_freq_').
"**eff**", "**lfm**", "**Pn**"
   Maximum CPU efficiency frequency (see 'max_eff_freq_').
"**Pm**"
   Minimum CPU operating frequency (see 'min_oper_freq_').

Mechanism
---------

MSR_HWP_REQUEST (**0x774**), bits **15:8**.

Scope
-----

This property has **CPU** scope.

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

Mechanism
---------
MSR_FSB_FREQ (**0xCD**), bits **2:0**. For platforms that don't support MSR_FSB_FREQ, **100.0MHz**
is used.

Scope
-----

This property has **package** scope. With the following exception, Silvermonts and Airmonts have
**module** scope.

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
to as **Pm**.

Mechanism
---------

MSR_PLATFORM_INFO (**0xCE**), bits **55:48**.

Scope
-----

This property has **CPU** scope.

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
referred to as **LFM** (Low Frequency Mode) or **Pn**.

Mechanism
---------

MSR_PLATFORM_INFO (**0xCE**), bits **47:40**.

Scope
-----

This property has **CPU** scope.

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

Location of the turbo knob in sysfs depends on the CPU frequency driver.

intel_pstate - "/sys/devices/system/cpu/intel_pstate/no_turbo"

acpi-cpufreq - "/sys/devices/system/cpu/cpufreq/boost"

Scope
-----

This property has **global** scope.

----------------------------------------------------------------------------------------------------

max_turbo_freq
==============

max_turbo_freq - Maximum CPU turbo frequency

Synopsis
--------

| pepc pstates *info* **--max-eff-freq**

Description
-----------

Maximum 1-core turbo frequency is the highest frequency a single CPU can operate at. This frequency
is also referred to as max. 1-core turbo and P01.

Mechanism
---------

MSR_TURBO_RATIO_LIMIT (**0x1AD**), bits **7:0**.

Scope
-----

This property has **CPU** scope.

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

The default unit is "**Hz**", but "**kHz**", "**MHz**", and "**GHz**" can also be used
(for example "900MHz").

The following special values are supported:

"**min**"
   Minimum uncore frequency supported (see 'min_freq_limit_').
"**max**"
   Maximum uncore frequency supported (see 'max_freq_limit_').
"**mdl**"
   Middle uncore frequency between minimum and maximum rounded to nearest 100MHz.

Mechanism
---------

"/sys/devices/system/cpu/intel_uncore_frequency/package\_\ **00**\ _die\_\ **01**\ /min_freq_khz",
'**00**' is replaced with desired package number and '**01**' with desired die number.

Scope
-----

This property has **die** scope.

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

The default unit is "**Hz**", but "**kHz**", "**MHz**", and "**GHz**" can also be used
(for example "900MHz").

The following special values are supported:

"**min**"
   Minimum uncore frequency supported (see 'min_freq_limit_').
"**max**"
   Maximum uncore frequency supported (see 'max_freq_limit_').
"**mdl**"
   Middle uncore frequency between minimum and maximum rounded to nearest 100MHz.

Mechanism
---------

"/sys/devices/system/cpu/intel_uncore_frequency/package\_\ **00**\ _die\_\ **01**\ /max_freq_khz",
'**00**' is replaced with desired package number and '**01**' with desired die number.

Scope
-----

This property has **die** scope.

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

"/sys/devices/system/cpu/intel_uncore_frequency/package\_\ **00**\ _die\_\ **01**\
/initial_min_freq_khz", '**00**' is replaced with desired package number and '**01**' with desired
die number.

Scope
-----

This property has **die** scope.

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

"/sys/devices/system/cpu/intel_uncore_frequency/package\_\ **00**\ _die\_\ **01**\
/initial_max_freq_khz", '**00**' is replaced with desired package number and '**01**' with desired
die number.

Scope
-----

This property has **die** scope.

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

MSR_PM_ENABLE (**0x770**), bit **0**.

Scope
-----

This property has **global** scope.

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

Mechanism
---------

"/sys/devices/system/cpu/cpufreq/policy\ **0**\ /energy_performance_preference", '**0**' is replaced
with desired CPU number.

Scope
-----

This property has **CPU** scope.

----------------------------------------------------------------------------------------------------

epp_hw
======

epp_hw - Energy Performance Preference

Synopsis
--------

| pepc pstates *info* **--epp-hw**
| pepc pstates *config* **--epp-hw**\ =<value>

Description
-----------

Energy Performance Preference is a hint to the CPU on energy efficiency vs performance. EPP value is
a number in range of 0-255 (maximum energy efficiency to maximum performance).

When package control is enabled the value is read from MSR_HWP_REQUEST_PKG 0x772, but when written
package control is disabled and value is written to MSR_HWP_REQUEST 0x774, both require the 'msr'
Linux kernel driver.

Mechanism
---------

MSR_HWP_REQUEST (**0x774**), bits **31:24**.

Scope
-----

This property has **CPU** scope.

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

Mechanism
---------

"/sys/devices/system/cpu/cpu\ **0**\ /power/energy_perf_bias", '**0**' is replaced with desired CPU
number.

Scope
-----

This property has **CPU** scope.

----------------------------------------------------------------------------------------------------

epb_hw
======

epb_hw - Energy Performance Preference

Synopsis
--------

| pepc pstates *info* **--epb-hw**
| pepc pstates *config* **--epb-hw**\ =<value>

Description
-----------

Energy Performance Bias is a hint to the CPU on energy efficiency vs performance. EBP value is a
number in range of 0-15 (maximum performance to maximum energy efficiency).

Mechanism
---------

MSR_ENERGY_PERF_BIAS (**0x1B0**), bits **3:0**.

Scope
-----

This property has **CPU** scope. With the following exceptions, Silvermonts have **core** scope,
Westmeres and Sandybridges have **package** scope.

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

"/sys/devices/system/cpu/cpufreq/policy\ **0**\ /scaling_driver", '**0**' is replaced with desired
CPU number.

Scope
-----

This property has **global** scope.

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

The 'intel_pstate' driver has 3 operation modes: '**active**', '**passive**' and '**off**'. The main
difference between the active and passive mode is in which frequency governors are used - the
generic Linux governors (passive mode) or the custom, built-in 'intel_pstate' driver governors
(active mode).

Mechanism
---------

"/sys/devices/system/cpu/intel_pstate/status"

Scope
-----

This property has **global** scope.

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

"/sys/devices/system/cpu/cpufreq/policy\ **0**\ /scaling_governor", '**0**' is replaced with desired
CPU number.

Scope
-----

This property has **CPU** scope.

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

"/sys/devices/system/cpu/cpufreq/policy\ **0**\ /scaling_available_governors", '**0**' is replaced
with desired CPU number.)

Scope
-----

This property has **global** scope.
