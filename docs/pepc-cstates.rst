.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

:Title: C-states

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

Retrieve C-state information for specified CPUs. By default, display all details for all CPUs. Use
target CPU specification options to limit the scope to specific CPUs, cores, dies, or packages.

**--yaml**
   Print information in YAML format.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   Comma-separated list of mechanisms to use for retrieving C-states information. Use
   '--list-mechanisms' to view available mechanisms. Many options support only one mechanism
   (e.g., 'sysfs'), while some support multiple (e.g., 'sysfs' and 'msr'). Mechanisms are tried
   in the specified order. By default, all mechanisms are allowed, with the most preferred tried
   first.

**--list-mechanisms**
   List available mechanisms for retrieving C-states information.

**--cstates** *[CSTATES]*
   Comma-separated list of C-states to retrieve information about, specified by name (e.g., C1).
   Use 'all' to include all available Linux C-states (default). Remember, Linux C-states (e.g., C6)
   are requests Linux can make, while hardware C-states (e.g., Core C6 or Package C6 on Intel
   platforms) are platform-specific states entered upon such requests. See the
   'https://github.com/intel/pepc/blob/main/docs/misc-cstate-namespaces.md' document for details.

**--pkg-cstate-limit**
   Retrieve the current package C-state limit, available limits, and lock status. The package
   C-state limit defines the deepest hardware package C-state the platform can enter. It is read
   from MSR_PKG_CST_CONFIG_CONTROL (0xE2), bits 2:0 or 3:0, depending on the CPU model. The lock
   bit (bit 15) in the same MSR determines if the OS can modify the limit.

**--c1-demotion**
   Check if C1 demotion is enabled or disabled. On Intel platforms, this feature monitors CPU
   wake-up rates. If the rate exceeds a threshold, deep C-state requests are demoted to C1 to
   improve performance, potentially increasing power consumption. Read from
   MSR_PKG_CST_CONFIG_CONTROL (0xE2), bit 26.

**--c1-undemotion**
   Check if C1 undemotion is enabled or disabled. When enabled, the CPU can reverse previously
   demoted requests from C1 back to deeper C-states (e.g., C6) if frequent wake-ups have stopped.
   Read from MSR_PKG_CST_CONFIG_CONTROL (0xE2), bit 28.

**--c1e-autopromote**
   Check if C1E autopromotion is enabled. When enabled, the CPU converts all C1 C-state requests
   to C1E requests. Read from MSR_POWER_CTL (0x1FC), bit 1.

**--cstate-prewake**
   Check if C-state prewake is enabled. When enabled, the CPU considers idle timers and starts
   exiting deep C-states early, before the next local APIC timer event. This ensures the CPU is
   nearly awake by the tim the timer fires. Read from MSR_POWER_CTL (0x1FC), bit 30.

**--idle-driver**
   Retrieve the idle driver name. The idle driver enumerates available C-states and issues
   C-state requests. Read from '/sys/devices/system/cpu/cpuidle/current_governor'.

**--governor**
   Retrieve the idle governor name, which determines the C-state to request for an idle CPU. Read
   from '/sys/devices/system/cpu/cpuidle/scaling_governor'.

**--governors**
   Retrieve the list of available idle governors, which determine the C-state to request for an
   idle CPU. Different governors implement various selection policies. Read from
   '/sys/devices/system/cpu/cpuidle/available_governors'.

Subcommand *'config'*
=====================

Configure C-states for specified CPUs. If no parameter is provided, the current configuration will
be displayed. Use target CPU specification options to limit the scope to specific CPUs, cores, dies,
or packages.

**-m** *MECHANISMS*, **--mechanisms** *MECHANISMS*
   Comma-separated list of mechanisms to use for configuring C-states. Use '--list-mechanisms' to
   view available mechanisms. Many options support only one mechanism (e.g., 'sysfs'), while some
   support multiple (e.g., 'sysfs' and 'msr'). Mechanisms are tried in the specified order. By
   default, all mechanisms are allowed, with the most preferred tried first.

**--list-mechanisms**
   List available mechanisms for configuring C-states.

**--enable** *CSTATES*
   Comma-separated list of C-state names to enable. Use 'all' to include all available Linux
   C-states (default). Remember, Linux C-states (e.g., C6) are requests Linux can make, while
   hardware C-states (e.g., Core C6 or Package C6 on Intel platforms) are platform-specific states
   entered upon such requests. See the
   'https://github.com/intel/pepc/blob/main/docs/misc-cstate-namespaces.md' document for details.

**--disable** *CSTATES*
   Similar to '--enable', but specifies the C-states to disable.

**--pkg-cstate-limit** *PKG_CSTATE_LIMIT*
   Set the package C-state limit, defining the deepest hardware package C-state the platform can
   enter. Writes to MSR_PKG_CST_CONFIG_CONTROL (0xE2), bits 2:0 or 3:0, depending on the CPU model.
   Writing is refused if the lock bit (bit 15) in the same MSR is set.

**--c1-demotion** *on|off*
   Enable or disable C1 demotion. On Intel platforms, this feature monitors CPU wake-up rates. If
   the rate exceeds a threshold, deep C-state requests are demoted to C1 to improve performance at
   the cost of higher power consumption. Writes to MSR_PKG_CST_CONFIG_CONTROL (0xE2), bit 26.

**--c1-undemotion** *on|off*
   Enable or disable C1 undemotion. When enabled, the CPU can reverse previously demoted C1
   requests back to deeper C-states (e.g., C6) if frequent wake-ups have stopped. Writes to
   MSR_PKG_CST_CONFIG_CONTROL (0xE2), bit 28.

**--c1e-autopromote** *on|off*
   Enable or disable C1E autopromotion. When enabled, all C1 C-state requests are converted to
   C1E. Writes to MSR_POWER_CTL (0x1FC), bit 1.

**--cstate-prewake** *on|off*
   Enable or disable C-state prewake. When enabled, the CPU considers idle timers and starts
   exiting deep C-states early, before the next local APIC timer event. This ensures the CPU is
   nearly awake by the tim the timer fires. Writes to MSR_POWER_CTL (0x1FC), bit 30.

**--governor** *NAME*
   Configure the idle governor, which decides the C-state to request for an idle CPU. Updates
   '/sys/devices/system/cpu/cpuidle/scaling_governor'.
