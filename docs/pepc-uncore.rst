.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: Uncore properties.

.. Contents::
   :depth: 2
..

===================
Command *'uncore'*
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

Target domain specification options
===================================

All sub-commans (*'info'*, *'config'*) support the following target domain specification options.

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
   indices or index ranges. For example, if a core includes CPUs 3 and 4, sibling index 0 refers to
   CPU 3 and index 1 refers to CPU 4. This option can only be used to reference online CPUs, because
   Linux does not provide topology information for offline CPUs. In the example with CPUs 3 and 4,
   if CPU 3 was offline, then index 0 would refer to CPU 4 and index 1 would be invalid.

**--module-siblings** *MODULE_SIBLINGS*
   Module siblings are CPUs sharing the same module. The list can include individual module sibling
   indices or index ranges. For example, if a module includes CPUs 3, 4, 5, and 6, index 0 refers to
   CPU 3, index 1 refers to CPU 4, and index 2 refers to CPU 5, and index 3 refers to CPU 6. This
   option can only be used to reference online CPUs, because Linux does not provide topology
   information for offline CPUs. In the example with CPUs 3, 4, 5 and 6, if CPU 4 was offline, then
   index 1 would refer to CPU 5, index 2 would refer to CPU 6, and index 3 would be invalid.

Subcommand *'info'*
===================

Retrieve uncore information for specified dies. By default, display all details for all dies. Use
target domain specification options to define a subset of CPUs, cores, dies, or packages.

**--yaml**
   Display output in YAML format.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   A comma-separated list of mechanisms for retrieving information. Use '--list-mechanisms' to
   view available mechanisms. Many options support only one mechanism (e.g., 'sysfs'), while
   others may support multiple (e.g., 'sysfs' and 'msr'). Mechanisms are tried in the specified
   order. By default, all mechanisms are allowed, and the most preferred ones are tried first.

**--list-mechanisms**
   Display available mechanisms for retrieving uncore information.

**--min-freq**
   Retrieve the minimum uncore frequency. The supported mechanisms are: 'sysfs', 'tpmi'.
   In case of the 'sysfs' mechanism, the sysfs path depends on what uncore driver is used. In case
   of the 'intel_uncore_frequency_tpmi' driver, use
   '/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/min_freq_khz'. In case of the
   'intel_uncore_frequency' driver, use
   '/sys/devices/system/cpu/intel_uncore_frequency/package\_<NUMBER>_die\_<NUMBER>/min_freq_khz'.

   The 'tpmi' mechanism uses the tpmi driver debugfs interface to access TPMI registers. The exact
   path depends on the target die number. Example of the debugfs file path is
   '/sys/kernel/debug/tpmi-0000:00:03.1/tpmi-id-02/mem_dump'

**--max-freq**
   Retrieve the maximum uncore frequency. Similar to '--min-freq', but for the maximum uncore
   frequency. Uses the same mechanisms as '--min-freq', but the sysfs mechanism uses the
   'max_freq_khz' file instead of 'min_freq_khz'.

**--min-freq-limit**
   Get minimum uncore frequency limit supported but the kernel. The supported mechanism is 'sysfs'.
   In case of the 'intel_uncore_frequency_tpmi' driver, read
   /sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/initial_min_freq_khz'. In case of
   the 'intel_uncore_frequency' driver, read
   '/sys/devices/system/cpu/intel_uncore_frequency/package\_<NUMBER>_die\_<NUMBER>/initial_min_freq_khz'.

   The 'tpmi' mechanism does not provide min/max uncore frequency limits, therefore not available.

**--max-freq-limit**
   Retrieve the maximum uncore frequency limit. Similar to '--min-freq-limit', but for the
   maximum uncore frequency limit. Uses the same mechanisms as '--min-freq-limit', but the
   sysfs mechanism uses the 'initial_max_freq_khz' file instead of 'initial_min_freq_khz'.

**--elc-low-zone-min-freq**
   Retrieve the ELC low zone minimum uncore frequency. The supported mechanisms are: 'sysfs', 'tpmi'.
   In case of the 'sysfs' mechanism read.
   '/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/elc_floor_freq_khz'.

   The 'tpmi' mechanism uses the tpmi driver debugfs interface to access TPMI registers. The exact
   path depends on the target die number. Example of the debugfs file path is
   '/sys/kernel/debug/tpmi-0000:00:03.1/tpmi-id-02/mem_dump'

   When the aggregate die utilization falls below or equals the ELC low threshold value
   (--elc-low-threshold), the die enters the ELC low zone. Its uncore frequency floor is set to
   the ELC low zone minimum frequency (--elc-low-zone-min-freq), unless the global minimum uncore
   frequency (--min-freq) is higher, in which case the global minimum uncore frequency is used as
   the floor.

**--elc-mid-zone-min-freq**
   Retrieve the ELC middle zone minimum uncore frequency. Only the 'tpmi' mechanism is supported.
   Reads the same TPMI debugfs files as '--elc-low-zone-min-freq'.

   When the aggregate die utilization is above the ELC low threshold value (--elc-low-threshold),
   but below the ELC high threshold value (--elc-high-threshold), the die enters the ELC middle
   zone. Its uncore frequency floor is set to the ELC middle zone minimum frequency
   (--elc-mid-zone-min-freq), unless the global minimum uncore frequency (--min-freq) is higher, in
   which case the global minimum uncore frequency is used as the floor.

**--elc-low-threshold**
   Get the uncore ELC low threshold. The threshold defines the aggregate die utilization percentage.
   When utilization falls below this threshold, the platform sets the uncore frequency floor to the
   low ELC frequency (subject to the the '--min-freq-limit' - if the limit is higher than the
   low ELC frequency, the limit is used as the floor instead).

   Supported mechanisms are: 'sysfs', 'tpmi'. The 'sysfs' mechanism reads the
   '/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/elc_low_threshold_percent'. The
   TPMI reads the same debugfs files as '--min-freq'.

**--elc-high-threshold**
   Get the uncore ELC high threshold. The threshold defines the aggregate die utilization
   percentage. When die utilization exceeds this threshold, the platform rapidly raises the uncore
   frequency until die utilization drops below the threshold or the frequency reaches the
   '--max-freq' limit. In addition, uncore frequency increases may be prevented by other
   constraints, such as thermal or power limits.

   Supported mechanisms are: 'sysfs', 'tpmi'. The 'sysfs' mechanism reads the
   '/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/elc_high_threshold_percent'. The
   TPMI reads the same debugfs files as '--max-freq'.

**--elc-high-threshold-status**
   Get the uncore ELC high threshold enabled/disabled status. If disabled, the high threshold is
   ignored and the platform manages uncore frequency using the default algorithm.

   Supported mechanisms are: 'sysfs', 'tpmi'. The 'sysfs' mechanism reads the
   '/sys/devices/system/cpu/intel_uncore_frequency/uncore<NUMBER>/elc_high_threshold_enable'. The
   TPMI reads the same debugfs files as '--max-freq'.

Subcommand *'config'*
=====================

Configure uncore proparties for specified dies. If no parameter is provided, the current value(s)
will be displayed. Use target domain specification options to define the subset of CPUs, cores,
dies, or packages.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   A comma-separated list of mechanisms allowed for configuring uncore properties. Use '--list-mechanisms'
   to view available mechanisms. Many options support only one mechanism (e.g., 'sysfs'), while
   some support multiple (e.g., 'sysfs' and 'msr'). Mechanisms are tried in the specified order.
   By default, all mechanisms are allowed, and the most preferred ones are tried first.

**--list-mechanisms**
   Display available mechanisms for configuring uncore properties.

**--min-freq** *MIN_FREQ*
   Set the minimum uncore frequency. The default unit is 'Hz', but 'kHz', 'MHz', and 'GHz' can also
   be used (for example '900MHz'). Uses the same mechanisms as described in the 'info' sub-command.

   The following special values can also be used:
   **min**
      Minimum uncore frequency supported (see '--min-freq-limit'). Regardless of the
      '--mechanisms' option, the 'sysfs' mechanism is always used to resolve 'min' to the actual
      minimum frequency.
   **max**
      Maximum uncore frequency supported (see '--max-freq-limit'). Regardless of the
      '--mechanisms' option, the 'sysfs' mechanism is always used to resolve 'max' to the actual
      maximum frequency.
   **mdl**
      The middle uncore frequency value between minimum and maximum rounded to nearest 100MHz.
      Regardless of the '--mechanisms' option, the 'sysfs' mechanism is always used to resolve 'mdl'
      to the actual middle frequency.

   Note, the 'tpmi' mechanism does not provide minimum or maximum uncore frequency limits (the
   allowed range). As a result, it is possible to set uncore frequency values outside the supported
   limits, such as setting the minimum frequency below the actual minimum limit. Use caution when
   configuring uncore frequencies with the 'tpmi' mechanism.

**--max-freq** *MAX_FREQ*
   Set the maximum uncore frequency. Uses the same mechanisms as described in the 'info'
   sub-command. Similar to '--min-freq', but applies to the maximum frequency.

**--elc-low-zone-min-freq**
   Set the ELC low zone minimum uncore frequency. Uses the same mechanisms as described in the
   'info' sub-command. Supports special values **min**, **max**, and **mdl**, similar to
   '--min-freq'.

**--elc-mid-zone-min-freq**
   Set the ELC middle zone minimum uncore frequency. Uses the same mechanisms as described in the
   'info' sub-command. Supports special values **min**, **max**, and **mdl**, similar to
   '--min-freq'.

**--elc-low-threshold**
   Set the uncore ELC low threshold. Same as in the 'info' sub-command, but sets the ELC low
   threshold.

**--elc-high-threshold**
   Set the uncore ELC high threshold. Same as in the 'info' sub-command, but sets the ELC high
   threshold.

**--elc-high-threshold-status**
   Set the uncore ELC high threshold enabled/disabled status. Same as in the 'info' sub-command, but
   sets the ELC high threshold status.
