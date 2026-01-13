.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: CPU P-states

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
   Be quiet (print only improtant messages like warnings).

**-d**
   Print debugging information.

**--debug-modules** *MODNAME[,MODNAME1,...]*
   While the '-d' option enables all debug messages, this option limits them to the specified
   modules. For example, '-d --debug-modules MSR' will only show debug messages from the 'MSR'
   module.

**--version**
   Print the version number and exit.

**-H** *HOSTNAME*, **--host** *HOSTNAME*
   Host name or IP address of the target system. The pepc command will be executed on this system
   using SSH, instead of running it locally. If not specified, the command will be run locally.

**-U** *USERNAME*, **--username** *USERNAME*
   Name of the user to use for logging into the remote host over SSH. The default user name is
   'root'.

**-K** *PRIVKEY*, **--priv-key** *PRIVKEY*
   Path to the private SSH key for logging into the remote host. Defaults to keys in standard paths
   like '$HOME/.ssh'.

**-T** *TIMEOUT*, **--timeout** *TIMEOUT*
   Timeout for establishing an SSH connection in seconds. Defaults to 8.

**-D** *DATASET*, **--dataset** *DATASET*
   This option is for debugging and testing. It specifies the dataset to use for emulating the host
   for running the command on. The datasets are available in 'pepc' source code repository.

   The argument can be a dataset path or name. If specified by name, the following locations are
   searched for the dataset.

   1. './tests/emul-data' in the program's directory
   2. '$PEPC_DATA_PATH/tests/emul-data'
   3. '$HOME/.local/share/pepc/tests/emul-data'
   4. '$VIRTUAL_ENV/share/tests/emul-data'
   5. '/usr/local/share/pepc/tests/emul-data'
   6. '/usr/share/pepc/tests/emul-data'

**--force-color**
   Force colorized output even if the output stream is not a terminal (adds ANSI escape codes).

**--print-man-path**
  Print path to pepc manual pages directory and exit. This path can be added to the 'MANPATH'
  environment variable to make the manual pages available to the 'man' tool.

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

Retrieve CPU P-states information for specified CPUs. By default, display all details for all CPUs.
Use target CPU specification options to define a subset of CPUs, cores, dies, or packages.

**--yaml**
   Display output in YAML format.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   A comma-separated list of mechanisms for retrieving information. Use '--list-mechanisms' to
   view available mechanisms. Many options support only one mechanism (e.g., 'sysfs'), while
   others may support multiple (e.g., 'sysfs' and 'msr'). Mechanisms are tried in the specified
   order. By default, all mechanisms are allowed, and the most preferred ones are tried first.

**--list-mechanisms**
   Display available mechanisms for retrieving CPU P-states information.

**--min-freq**
   Retrieve the minimum CPU frequency from
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/scaling_min_freq'.

**--max-freq**
   Retrieve the maximum CPU frequency from
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/scaling_max_freq'.

**--min-freq-limit**
   Retrieve the minimum supported CPU frequency from
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/cpuinfo_min_freq'.

**--max-freq-limit**
   Retrieve the maximum supported CPU frequency from
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/cpuinfo_max_freq'.

**--hwp**
   Check if hardware power management is enabled. When enabled, CPUs can scale their frequency
   automatically without OS involvement. Mechanism: 'msr', reads MSR_PM_ENABLE (0x770), bit 0.
   This setting has global scope.

**--frequencies**
   List CPU frequencies supported by the Linux kernel for '--min-freq' and '--max-freq' options.
   If '/sys/devices/system/cpu/cpufreq/policy<NUMBER>/scaling_available_frequencies' is available
   (usually the case with the 'acpi_cpufreq' driver), retrieve the data from there. Otherwise,
   in case of an Intel platform, assume that all frequencies from '--min-freq-limit' to
   '--max-freq-limit' are available with a step equal to '--bus-clock'.

**--base-freq**
   Retrieve the base CPU frequency from
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/base_frequency'. If the file is unavailable, it
   falls back to '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/bios_limit'.

**--fixed-base-freq**
   Retrieve the CPU fixed base frequency from MSR_PLATFORM_INFO (0xCE), bits 15:8.

**--bus-clock**
   Retrieve the bus clock frequency, one of the CPU's reference clocks. The 'msr' mechanism reads
   MSR_FSB_FREQ (0xCD), bits 2:0, for legacy Intel platforms. For modern Intel platforms, the 'doc'
   mechanism assumes a 100MHz bus clock.

**--turbo**
   Check if turbo is enabled or disabled. When enabled, CPUs can run at frequencies above the base
   frequency if allowed by the OS and thermal conditions. Reads the sysfs file based on the CPU
   frequency driver: intel_pstate - '/sys/devices/system/cpu/intel_pstate/no_turbo', acpi-cpufreq -
   '/sys/devices/system/cpu/cpufreq/boost'. The setting has global scope.

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
   Retrieve the CPU frequency driver name. The driver enumerates and manages CPU P-states on the
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

**--cppc-lowest-perf**
   Retrieve the ACPI CPPC lowest performance level value for specified CPUs from
   '/sys/devices/system/cpu/cpu<NUMBER>/acpi_cppc/lowest_perf'.

**--cppc-lowest-nonlinear-perf**
   Retrieve the ACPI CPPC lowest nonlinear performance level value for specified CPUs from
   '/sys/devices/system/cpu/cpu<NUMBER>/acpi_cppc/lowest_nonlinear_perf'.

**--cppc-guaranteed-perf**
   Retrieve the ACPI CPPC guaranteed performance level value for specified CPUs from
   '/sys/devices/system/cpu/cpu<NUMBER>/acpi_cppc/guaranteed_perf'.

**--cppc-nominal-perf**
   Retrieve the ACPI CPPC nominal performance level value for specified CPUs from
   '/sys/devices/system/cpu/cpu<NUMBER>/acpi_cppc/nominal_perf'.

**--cppc-highest-perf**
   Retrieve the ACPI CPPC highest performance level value for specified CPUs from
   '/sys/devices/system/cpu/cpu<NUMBER>/acpi_cppc/highest_perf'.

**--cppc-nominal-freq**
   Retrieve the ACPI CPPC nominal frequency for specified CPUs from
   '/sys/devices/system/cpu/cpu<NUMBER>/acpi_cppc/nominal_freq'.

**--hwp-lowest-perf**
   Retrieve the HWP lowest performance level for specified CPUs. Reads MSR_HWP_CAPABILITIES (0x771),
   bits 31:24.

**--hwp-efficient-perf**
   Retrieve the HWP most efficient performance level for specified CPUs. Reads
   MSR_HWP_CAPABILITIES (0x771), bits 23:16.

**--hwp-guaranteed-perf**
   Retrieve the HWP guaranteed performance level for specified CPUs. Reads MSR_HWP_CAPABILITIES (0x771),
   bits 15:8.

**--hwp-highest-perf**
   Retrieve the HWP highest performance level for specified CPUs. Reads MSR_HWP_CAPABILITIES (0x771),
   bits 7:0.

Subcommand *'config'*
=====================

Configure CPU P-states for specified CPUs. If no parameter is provided, the current value(s) will be
displayed. Use target CPU specification options to define the subset of CPUs, cores, dies, or
packages.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   A comma-separated list of mechanisms allowed for configuring CPU P-states. Use
   '--list-mechanisms' to view available mechanisms. Many options support only one mechanism (e.g.,
   'sysfs'), while some support multiple (e.g., 'sysfs' and 'msr'). Mechanisms are tried in the
   specified order.  By default, all mechanisms are allowed, and the most preferred ones are tried
   first.

**--list-mechanisms**
   Display available mechanisms for configuring CPU P-states.

**--min-freq** *MIN_FREQ*
   Set the minimum CPU frequency via '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/scaling_min_freq'.
   The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also be used (for example "900MHz").

   The following special values can also be used:
   **min**
      Minimum frequency supported by the Linux CPU frequency driver (see '--min-freq-limit').
   **max**
      Maximum frequency supported by the Linux CPU frequency driver (see '--max-freq-limit').
   **base**, **hfm**
      Base CPU frequency (see '--base-freq').

**--max-freq** *MAX_FREQ*
   Similar to '--min-freq', but sets the maximum CPU frequency via
   '/sys/devices/system/cpu/cpu<NUMBER>/cpufreq/scaling_max_freq'.

**--turbo** *on|off*
   Toggle turbo mode globally via sysfs. When enabled, CPUs can exceed the base frequency if allowed
   by the OS and thermal conditions. In case of 'intel_pstate' driver, use
   '/sys/devices/system/cpu/intel_pstate/no_turbo', in case of 'acpi-cpufreq' driver, use
   '/sys/devices/system/cpu/cpufreq/boost'.

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
