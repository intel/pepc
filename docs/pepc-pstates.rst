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
   4. '$VIRTUAL_ENV/share/tests/data'
   5. '/usr/local/share/pepc/tests/data'
   6. '/usr/share/pepc/tests/data'

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

All sub-commans (*'info'*, *'config'*) support the following target CPU specification
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

Retrieve P-states information for specified CPUs. By default, display all details for all CPUs. Use
target CPU specification options to define a subset of CPUs, cores, dies, or packages.

**--yaml**
   Display output in YAML format.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   A comma-separated list of mechanisms for retrieving information. Use '--list-mechanisms' to
   view available mechanisms. Many options support only one mechanism (e.g., 'sysfs'), while
   others may support multiple (e.g., 'sysfs' and 'msr'). Mechanisms are tried in the specified
   order. By default, all mechanisms are allowed, and the most preferred ones are tried first.

**--list-mechanisms**
   Display available mechanisms for retrieving P-states information.

**--min-freq**
   Retrieve the minimum CPU frequency using 'sysfs' (preferred) or 'msr'. The 'sysfs' mechanism reads
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/scaling_min_freq', while 'msr' reads the MSR_HWP_REQUEST
   (0x774) register, bits 7:0.

**--max-freq**
   Retrieve the maximum CPU frequency using 'sysfs' (preferred) or 'msr'. The 'sysfs' mechanism reads
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/scaling_max_freq', while 'msr' reads the MSR_HWP_REQUEST
   (0x774) register, bits 15:8.

**--min-freq-limit**
   Retrieve the minimum CPU frequency supported by the Linux kernel from
   "/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/cpuinfo_min_freq".

**--max-freq-limit**
   Retrieve the maximum CPU frequency supported by the Linux kernel from
   "/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/cpuinfo_max_freq".

**--frequencies**
   List CPU frequencies supported by the Linux kernel for '--min-freq' and '--max-freq' options.
   If '/sys/devices/system/cpu/cpufreq/policy<NUMBER>/scaling_available_frequencies' is available
   (usually the case with the 'acpi_cpufreq' driver), retrieve the data from there. Otherwise,
   in case of an Intel platform, assume that all frequencies from '--min-freq-limit' to
   '--max-freq-limit' are available with a step equal to '--bus-clock'.

**--base-freq**
   Retrieve the base CPU frequency, also known as the "guaranteed frequency," HFM (High Frequency
   Mode), or P1. Preferred mechanism is 'sysfs', which reads
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/base_frequency'. If unavailable, it falls back to
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/bios_limit'. The 'msr' mechanism reads it from
   MSR_HWP_CAPABILITIES (0x771), bits 15:8 if CPU hardware power management is enabled, otherwise
   from MSR_PLATFORM_INFO (0xCE), bits 15:8.

**--bus-clock**
   Retrieve the bus clock frequency, one of the CPU's reference clocks. The 'msr' mechanism reads
   MSR_FSB_FREQ (0xCD), bits 2:0, for legacy Intel platforms. For modern Intel platforms, the 'doc'
   mechanism assumes a 100MHz bus clock.

**--min-oper-freq**
   Retrieve the minimum CPU operating frequency, the lowest frequency the CPU can operate at. This
   frequency, also known as Pm, may not always be directly available to the OS but can be used by
   the platform in certain scenarios (e.g., some C-states). Mechanism: 'msr', reads MSR_PLATFORM_INFO
   (0xCE), bits 55:48.

**--max-eff-freq**
   Retrieve the maximum CPU efficiency frequency, also known as LFM (Low Frequency Mode) or Pn.
   Mechanism: 'msr', reads MSR_HWP_CAPABILITIES (0x771), bits 23:16 on if CPU hardware power
   management is enabled, otherwise reads MSR_PLATFORM_INFO (0xCE), bits 47:40.

**--turbo**
   Check if turbo is enabled or disabled. When enabled, CPUs can run at frequencies above the base
   frequency if allowed by the OS and thermal conditions. Reads the sysfs file based on the CPU
   frequency driver: intel_pstate - '/sys/devices/system/cpu/intel_pstate/no_turbo', acpi-cpufreq -
   '/sys/devices/system/cpu/cpufreq/boost'. The setting has global scope.

**--max-turbo-freq**
   Retrieve the maximum turbo frequency, the highest frequency a single CPU can achieve. Also known
   as max 1-core turbo or P01. Mechanism: 'msr', reads MSR_HWP_CAPABILITIES (0x771), bits 7:0 if
   hardware power management is enabled, otherwise reads MSR_TURBO_RATIO_LIMIT (0x1AD), bits 7:0.

**--min-uncore-freq**
   Retrieve the minimum uncore frequency. In case of the 'intel_uncore_frequency_tpmi' driver, read
   '/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/min_freq_khz'. In case of the
   'intel_uncore_frequency' driver, read
   '/sys/devices/system/cpu/intel_uncore_frequency/package\_<NUMBER>_die\_<NUMBER>/min_freq_khz'.

**--max-uncore-freq**
   Retrieve the maximum uncore frequency. In case of the 'intel_uncore_frequency_tpmi' driver, read
   '/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/max_freq_khz'. In case of the
   'intel_uncore_frequency' driver, read
   '/sys/devices/system/cpu/intel_uncore_frequency/package\_<NUMBER>_die\_<NUMBER>/max_freq_khz'.

**--min-uncore-freq-limit**
   Get minimum uncore frequency limit supported but the kernel. In case of the
   'intel_uncore_frequency_tpmi' driver, read
   /sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/initial_min_freq_khz'. In case of
   the 'intel_uncore_frequency' driver, read
   '/sys/devices/system/cpu/intel_uncore_frequency/package\_<NUMBER>_die\_<NUMBER>/initial_min_freq_khz'.

**--max-uncore-freq-limit**
   Get maximum uncore frequency limit supported but the kernel. In case of the
   'intel_uncore_frequency_tpmi' driver, read
   /sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/initial_max_freq_khz'. In case of
   the 'intel_uncore_frequency' driver, read
   '/sys/devices/system/cpu/intel_uncore_frequency/package\_<NUMBER>_die\_<NUMBER>/initial_max_freq_khz'.

**--hwp**
   Check if hardware power management is enabled. When enabled, CPUs can scale their frequency
   automatically without OS involvement. Mechanism: 'msr', reads MSR_PM_ENABLE (0x770), bit 0.
   This setting has global scope.

**--epp**
   Retrieve EPP (Energy Performance Preference) using 'sysfs' (preferred) or 'msr' mechanisms. EPP
   is a hint to the CPU on energy efficiency vs performance. The value ranges from 0-255 (maximum
   energy efficiency to maximum performance) or can be a policy name (supported by 'sysfs' only).
   The 'sysfs' mechanism reads
   '/sys/devices/system/cpu/cpufreq/policy<NUMBER>/energy_performance_preference', while the 'msr'
   mechanism reads MSR_HWP_REQUEST (0x774), bits 31:24.

**--epb**
   Retrieve EPB (Energy Performance Bias) using 'sysfs' (preferred) or 'msr' mechanisms. EPB is a
   hint to the CPU on energy efficiency versus performance. The value ranges from 0-15 (maximum
   performance to maximum energy efficiency) or can be a policy name (supported by 'sysfs' only).
   The 'sysfs' mechanism reads '/sys/devices/system/cpu/cpu<NUMBER>/power/energy_perf_bias', while
   the 'msr' mechanism reads MSR_ENERGY_PERF_BIAS (0x1B0), bits 3:0.

**--driver**
   Retrieve the CPU frequency driver name. The driver enumerates and manages P-states on the
   platform. The name is read from '/sys/devices/system/cpu/cpufreq/policy<NUMBER>/scaling_driver'.
   While sysfs provides a per-CPU API, Intel platforms typically use a single driver.

**--intel-pstate-mode**
   Retrieve the 'intel_pstate' driver mode: 'active', 'passive', or 'off'. In 'active' mode, custom
   'intel_pstate' governors are used. In 'passive' mode, generic Linux governors are employed.
   The mode is read from '/sys/devices/system/cpu/intel_pstate/status'.

**--governor**
   Retrieve the CPU frequency governor, which determines the P-state based on CPU load and other
   factors. The governor name is read from
   '/sys/devices/system/cpu/cpufreq/policy<NUMBER>/scaling_governor'.

**--governors**
   Retrieve the list of available CPU frequency governors. Governors determine the P-state of a CPU
   based on its activity and other factors, each implementing a unique selection policy. Available
   governors are listed in
   '/sys/devices/system/cpu/cpufreq/policy<NUMBER>/scaling_available_governors'.

Subcommand *'config'*
=====================

Configure P-states for specified CPUs. If no parameter is provided, the current value(s) will be
displayed. Use target CPU specification options to define the subset of CPUs, cores, dies, or
packages.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   A comma-separated list of mechanisms allowed for configuring P-states. Use '--list-mechanisms'
   to view available mechanisms. Many options support only one mechanism (e.g., 'sysfs'), while
   some support multiple (e.g., 'sysfs' and 'msr'). Mechanisms are tried in the specified order.
   By default, all mechanisms are allowed, and the most preferred ones are tried first.

**--list-mechanisms**
   Display available mechanisms for configuring P-states.

**--min-freq** *MIN_FREQ*
   Set the minimum CPU frequency. The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also be
   used (for example "900MHz"). Preferred mechanism is 'sysfs', which uses
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/scaling_min_freq'. The 'msr' mechanism uses the
   MSR_HWP_REQUEST (0x774) register, bits 7:0.

   The following special values can also be used:
   **min**
      Minimum frequency supported by the Linux CPU frequency driver (see '--min-freq-limit').
   **max**
      Maximum frequency supported by the Linux CPU frequency driver (see '--max-freq-limit').
   **base**, **hfm**, **P1**
      Base CPU frequency (see '--base-freq').
   **eff**, **lfm**, **Pn**
      Maximum CPU efficiency frequency (see '--max-eff-freq').
   **Pm**
      Minimum CPU operating frequency (see '--min-oper-freq').

   Note, on some systems 'Pm' is lower than 'Pn'. For example, 'Pm' may be 500MHz, while 'Pn' may
   be 800MHz. On such systems, Linux may use 'Pn' as the minimum supported frequency limit. From
   Linux's perspective, the minimum frequency could be 800MHz, not 500MHz. In this case, using
   '--min-freq 500MHz --mechanisms sysfs' will fail, while '--min-freq 500MHz --mechanisms msr'
   will succeed. By default, '--min-freq 500MHz' will also succeed as pepc tries all available
   mechanisms.

**--max-freq** *MAX_FREQ*
   Set the maximum CPU frequency. Similar to '--min-freq', but applies to the maximum frequency.

**--turbo** *on|off*
   Toggle turbo mode globally via sysfs. When enabled, CPUs can exceed the base frequency if allowed
   by the OS and thermal conditions. In case of 'intel_pstate' driver, use
   '/sys/devices/system/cpu/intel_pstate/no_turbo', in case of 'acpi-cpufreq' driver, use
   '/sys/devices/system/cpu/cpufreq/boost'.

**--min-uncore-freq** *MIN_UNCORE_FREQ*
   Set the minimum uncore frequency. The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also
   be used (for example '900MHz'). In case of the 'intel_uncore_frequency_tpmi' driver, use
   '/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/min_freq_khz'. In case of the
   'intel_uncore_frequency' driver, use
   '/sys/devices/system/cpu/intel_uncore_frequency/package\_<NUMBER>_die\_<NUMBER>/min_freq_khz'.

   The following special values can also be used:
   **min**
      Minimum uncore frequency supported (see '--min-freq-limit').
   **max**
      Maximum uncore frequency supported (see '--max-freq-limit').
   **mdl**
      Middle uncore frequency between minimum and maximum rounded to nearest 100MHz.

**--max-uncore-freq** *MAX_UNCORE_FREQ*
   Set the maximum uncore frequency. Similar to '--min-uncore-freq', but applies to the maximum
   frequency.

**--epp** *EPP*
   Set EPP (Energy Performance Preference) using 'sysfs' (preferred) or 'msr' mechanisms. EPP
   is a hint to the CPU on energy efficiency vs performance. The value ranges from 0-255 (maximum
   energy efficiency to maximum performance) or can be a policy name (supported by 'sysfs' only).
   The 'sysfs' mechanism writes to
   '/sys/devices/system/cpu/cpufreq/policy<NUMBER>/energy_performance_preference', while the 'msr'
   mechanism writes to MSR_HWP_REQUEST (0x774), bits 31:24.

**--epb** *EPB*
   Set EPB (Energy Performance Bias) using 'sysfs' (preferred) or 'msr' mechanisms. EPB is a
   hint to the CPU on energy efficiency versus performance. The value ranges from 0-15 (maximum
   performance to maximum energy efficiency) or can be a policy name (supported by 'sysfs' only).
   The 'sysfs' mechanism writes to '/sys/devices/system/cpu/cpu<NUMBER>/power/energy_perf_bias',
   while the 'msr' mechanism writes to MSR_ENERGY_PERF_BIAS (0x1B0), bits 3:0.

**--intel-pstate-mode** *[MODE]*
   Set the 'intel_pstate' driver mode: 'active', 'passive', or 'off'. In 'active' mode, custom
   'intel_pstate' governors are used. In 'passive' mode, generic Linux governors are employed.
   Writes to '/sys/devices/system/cpu/intel_pstate/status'.

**--governor** *[NAME]*
   Set the CPU frequency governor, which determines the P-state based on CPU load and other factors.
   Writes to '/sys/devices/system/cpu/cpufreq/policy<NUMBER>/scaling_governor'.
