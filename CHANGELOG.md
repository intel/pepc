# Changelog

Changelog practices: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning practices: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [ADD NEW VERSION HERE] - ADD DATE HERE
### Fixed
### Added
### Removed
### Changed

## [1.6.19] - 2026-01-25
### Added
 - pepc tpmi * --base option support.

## [1.6.18] - 2026-01-23
### Added
 - pepc tpmi ls --list-specs.
### Changed
 - Improved tpmi command documentation.

## [1.6.17] - 2026-01-19
### Added
 - Add a new article about base frequency.
### Changed
 - Extend and improve documentation and man pages.

## [1.6.16] - 2026-01-14
### Fixed
 - pepc tpmi read: Do not read dead instances.

## [1.6.15] - 2026-01-14
### Fixed
 - pepc tpmi read: Fix bit-fields print format.

## [1.6.14] - 2026-01-14
### Added
 - 'pepc pstates info --fixed-base-perf'.
 - 'pepc pstates info --cppc-nominal-perf' and other CPPC performance levels
   support.
 - 'pepc pstates info --hwp-guaranteed-perf' and other HWP performance levels
   support.
### Removed
 - Stop trying to mimic sysfs frequency via MSRs.

## [1.6.13] - 2026-01-08
### Fixed
 - Fix 'pepc pstates' crash on Lunar Lake.
### Added
 - Make 'info' commands (e.g. pepc pstates info) not fail when permission is
   denied to read certain properties. Instead, print "Permission denied" for
   such properties and continue.

## [1.6.12] - 2025-12-22
### Fixed
 - Multiple minor bug fixes in 'pepc tpmi'.

## [1.6.11] - 2025-12-20
### Added
 - Refresh TPMI spec files.
 - Add a mechanism for per-platform TPMI spec files.

## [1.6.10] - 2025-10-22
### Fixed
 - Fix remote mode (-H) crash on some Ubuntu systems.

## [1.6.9] - 2025-10-09
### Added
 - Add package C-states limit support for Panther Lake.

## [1.6.8] - 2025-10-02
### Fixed
 - Fix --c1-demotion/undemotion for ICX, SPR, and EMR.

## [1.6.7] - 2025-09-30
### Fixed
 - Fix C-states detection on systems with only 1 C-state.
 - Bugfixes in --core-siblings option handling.

## [1.6.6] - 2025-09-22
### Fixed
 - Fix 1.6.1 regression: Failure to enable/disable C-states.

## [1.6.5] - 2025-09-21
### Fixed
 - Fix minor regression since v1.6.3: junk traceback on errors.

## [1.6.4] - 2025-09-19
### Fixed
 - Add a crash in 'KernelVersion.py' introduced in v1.6.3.

## [1.6.3] - 2025-09-19
### Fixed
 - Fix 1.6.1 regression: C-states were always reported as disabled.
 - Fix 'pepc pmqos config --latency-limit', which always crashed.

## [1.6.2] - 2025-09-16
### Fixed
 - Improve 'importlib_resources' failure message in case of python 3.9.

## [1.6.1] - 2025-09-10
### Fixed
 - Fix Arrow Lake frequency reading with the 'msr' method.
 - Fix base frequency reading on some systems using 'acpi-cpufreq'.

## [1.6.0] - 2025-09-05
### Fixed
 - Fix crashes with python 3.9.
### Added
 - Uncore ELC options and user document.
### Removed
 - Remove the '--max-eff-freq' option.
### Changed
 - Separate out uncore options from 'pepc pstates' to 'pepc uncore'.

## [1.5.44] - 2025-08-27
### Fixed
 - Fix 'pepc pstates info' broken since version 1.5.42.

## [1.5.43] - 2025-08-27
### Fixed
 - Fixes for the newly added "tpmi" uncore frequency mechanism.
### Changed
 - Improve uncore frequency documentation sections.

## [1.5.42] - 2025-08-26
### Fixed
 - Fix the '--debug-modules' option, which printed every message twice.
### Added
 - Add uncore frequency support via TPMI.
 - Add an article about CPU frequency and C1E.

## [1.5.41] - 2025-08-19
### Changed
 - Just minor helper module improvements to support derived projects.
 - Add an article about C6P C-state.

## [1.5.40] - 2025-07-14
### Added
 - Add Clearwater Forest support.

## [1.5.39] - 2025-06-06
### Fixed
 - Fix hybrid core type detiction in 'pepc topology info'.
 - Fix 'pepc print pstates --mechanisms msr,cppc' and similar use-cases.
### Added
 - Add LPE cores support.
 - Improve output on hybryd systems: specify core types.
### Removed
 - Remove 'pepc power' command.
 - Remove package C-state aliases output.

## [1.5.38] - 2025-05-28
### Fixed
 - Fix searching for data files. This fixes a wult regression.

## [1.5.37] - 2025-05-27
### Fixed
 - Fix crash because of unimported 'PropertyTypedDict' symbol.

## [1.5.36] - 2025-05-22
### Fixed
 - Fix versioning bug that made anything newer than 1.5.32 install incorrectly
   in some scenarios.
 - Fix failures with python 3.9.
### Added
 - New '--debug-modules' option to limit debug prints to certain modules list.
 - New '--print-man-path' to print the path to man pages.
### Changed
 - Rework packaging: switch from setup.py to pyproject.toml.
 - Install pepc data (man pages, TPMI files) to "../site-packages/pepcdata".

## [1.5.35] - 2025-05-16
### Fixed
 - Remove forgotted debug print.

## [1.5.34] - 2025-05-16
### Fixed
 - Fix 'pepc cstates info --min-oper-freq' reporting incorrect numbers.
### Removed
 - Changed '--frequencies' mechanism from docs to sysfs.

## [1.5.33] - 2025-05-06
### Changed
 - Improve man pages, documentation, add a couple of new documents about
   C-states and MSR scope.

## [1.5.32] - 2025-04-07
### Changed
 - Fixes in SSH process manager library that affect the 'wult' project.

## [1.5.31] - 2025-03-25
### Added
 - Support python "VIRTUAL_ENV" environment variable in 'wult deploy'.

## [1.5.30] - 2025-03-14
### Changed
 - Minor changes to support dependent projects.

## [1.5.29] - 2025-03-11
### Changed
 - Minor changes to support dependent projects.

## [1.5.28] - 2025-03-05
### Fixed
 - Fix crash when paramiko and colorama packages are not installed.

## [1.5.27] - 2025-02-27
### Changed
 - No functional changes, improvements to support dependent projects.

## [1.5.26] - 2025-01-27
### Fixed
 - Fix compatibility with python <= 3.10.

## [1.5.25] - 2025-01-16
### Fixed
 - Fix another crash caused by a typo in v1.5.23.

## [1.5.24] - 2025-01-16
### Fixed
 - Fix crashes caused by typos in v1.5.23.

## [1.5.23] - 2025-01-15
### Fixed
 - Fix frequency reporting via MSR on Meteor Lake and Lunar Lake.
### Added
 - Add PM QoS support.
 - Require python version 3.9 (was 3.8).

## [1.5.22] - 2025-01-05
### Fixed
  - Fix min. and max. uncore frequency support on Granite Rapids and Sierra
    Forest Xeons.

## [1.5.21] - 2024-11-29
### Fixed
  - Fix the '--list-mechanisms' option.
  - Fix 'pepc topology info' crash on multi-package systems with all CPUs
    offline on one or more packages.
### Added
  - Add Clearwater Forest Xeon support.

## [1.5.20] - 2024-09-16
### Changed
 - Improve error message for 'pepc pstates config --epp=<value>' failing with
   the performance governor.

## [1.5.19] - 2024-08-29
 - Minor change required to support the 'wult' project. No 'pepc' tool
   functionality changes.

## [1.5.18] - 2024-08-16
### Changed
 - Minor change required to support the 'stats-collect' project. No 'pepc' tool
   functionality changes.

## [1.5.17] - 2024-07-24
### Fixed
 - Fix failure when '--dies all' or '--cores all' is specified without
   specifying package numbers.

## [1.5.16] - 2024-06-19
### Changed
 - Update the uncore TPMI spec file to include UFS latency control registers.

## [1.5.15] - 2024-06-05
### Removed
 - Remove the 'pepc cstates --pch-negotiation' option.
### Changed
 - Improve 'pepc topology info' output and avoid printing identical lines many
   times.
 - Improve '--cores' and '--dies' options handling: do not require '--packages'
   option if there is no abiguity.

## [1.5.14] - 2024-04-25
### Changed
 - Misc. changes in shared modules to support dependent projects, such as
   'stats-collect'. No 'pepc' tool functional changes.

## [1.5.13] - 2024-04-11
### Fixed
 - Critical fix: address incorrect 'pepc pastates config --min-uncore-freq'
   behavior on Grand Ridge, Sierra Forest and Granite Rapids platforms.

## [1.5.12] - 2024-04-09
### Fixed
 - Critical fix: address the issue of the 'pepc tpmi write' operation writing
   incorrect values in some cases.

## [1.5.11] - 2024-04-09
### Changed
 - Minor change: do not print a message about missing package C-states table.
   Often it is missing for a good reason, like on the Snow Ridge or Grand
   Ridge.

## [1.5.10] - 2024-03-27
### Fixed
 - Fix TPMI spec files loading defect to ensure 'PEPC_TPMI_DATA_PATH' mechanism
   works.

## [1.5.9] - 2024-03-19
### Fixed
 - Fix the following options of 'pepc pstates info' on some systems:
   '--base-freq', '--max-eff-freq', '--min-oper-freq', '--max-turbo-freq'.

## [1.5.8] - 2024-03-08
### Changed
 - Dummy release, no changes comparing to 1.5.8.

## [1.5.7] - 2024-03-08
### Added
 - Add 'pepc tpmi read' and 'pepc tpmi write' commands.

## [1.5.6] - 2024-02-19
### Fixed
 - Workaround for connecting to remote hosts becaulse of paramiko failing in
   Fedora 39.

## [1.5.5] - 2024-02-09
### Added
 - New command: pepc tpmi. Only the "ls" sub-command is implemented so far.
### Changed
 - Improve multi-CPU MSR read speed for the remote usage scenario.

## [1.5.4] - 2024-01-22
### Fixed
 - Fix incorrect uncore frequency configure result on systems that use the TPMI
   uncore frequency driver (regression since v1.5.0).

## [1.5.3] - 2024-01-22
### Fixed
 - Fix uncore frequency configuration failure (regression since v1.5.0).
### Added
 - Add the '--l1-aspm' option to 'pepc aspm' to get/set L1 ASPM for
   individual PCI devices.

## [1.5.2] - 2024-01-11
### Fixed
 - Improve formatting of values in 'pepc info' commands.
 - Fix warning when using the '--pkg-cstate-limit' option (regression
   introduced in v1.5.1).

## [1.5.1] - 2024-01-08
### Fixed
 - Fix a crash when user specifies certain incorrect CPU frequency values
   (regression introduced in v1.5.0).

## [1.5.0] - 2024-01-07
### Added
 - Support setting uncore frequency for I/O dies.

## [1.4.45] - 2023-12-22
### Added
 - Improve 'pepc topology info' to include I/O dies to the output.

## [1.4.44] - 2023-12-21
### Fixed
 - Fix multiple bugs on systems that have I/O dies.

## [1.4.43] - 2023-12-20
### Fixed
 - Fix C-state printing with '--yaml' opiton.
 - Fix 'pepc pstates config' failing with 'mdl' CPU and uncore frequency value.
### Changed
 - Refer to packages and dies when printing about per-package and per-die
   properties, instead for referring to CPU numbers.

## [1.4.42] - 2023-11-24
### Added
 - Minor logger improvement to satisfy 'wult' project needs.

## [1.4.41] - 2023-11-22
### Fixed
  - Fix 'pepc power config --ppl2' faling on some system with a "PPL2 value out
    of range" error message.

## [1.4.40] - 2023-11-20
### Fixed
 - Fix uncore module probing on non-Intel systems.

## [1.4.39] - 2023-11-19
### Added
 - Add '--modules' and '--dies' options to all commands that support '--cores' option. The new
   options allow for specifying module and die numbers.
### Changed
 - 'pepc * info' commands do not print CPU numbers when a property has the same
   value for all CPUs. Instead, just "all CPUs" is printed. This makes output
   less cluttered.

## [1.4.38] - 2023-11-07
### Added
 - Add '--mechanism' option, which can be used for specifying the mechanism for
   getting and setting pepc C-states, P-states, and Power options.
 - Add '--list-mechanisms' option for listing all the available mechanisms.
 - Add new '--frequencies' option for listing CPU frequencies acceptable but
   the Linux driver.
 - Add new 'cppc' mechanism, which can read ACPI CPPC CPU frequency data.
### Removed
 - Remove '--epb-hw' and '--epp-hw' options. They are replaced with '--epb' and
   '-epp' plus the '--mechanism msr' options combination.
 - Remove '--min-freq-hw' and '--max-freq-hw' options. They are replaced with
   '--min-freq' and '-max-freq' plus the '--mechanism msr' options combination.
### Changed
 - The 'pepc aspm info' command now has separate '--policy' and '--policies'
   options.

## [1.4.37] - 2023-10-25
### Fixed
 - Fix regression in v1.4.36: 'pepc cstates|pstates|power config' does not print
   information about changed options.
### Added
 - Add '--pch-negotiation' option for 'pepc cstates' command.

## [1.4.36] - 2023-10-18
### Fixed
 - pepc cstates: when system has no C-states (e.g., booted with idle=poll), do
   not error out, just print that there are no C-states.
### Added
 - pepc pstates: add "mdl" special uncore frequency value support.

## [1.4.35] - 2023-10-04
### Added
 - Add 'base_frequency' support for AMD systems.

## [1.4.34] - 2023-09-28
### Changed
 - Improve scaling printed values with SI prefixes (e.g., print 2.44ms instead
   of 0.00244140625s.
 - Improve readability by printing numeric values without using quotes.

## [1.4.33] - 2023-09-08
### Fixed
 - Fix 'pepc pstates info' output, group the properties by source.
### Added
 - Add new methods to 'CPUInfo' module to support 'wult' project needs.

## [1.4.32] - 2023-08-17
### Removed
 - pepc cstates info: remove '--pkg-cstate-limits', '--pkg-cstate-limit-lock',
   and '--pkg-cstate-limit-aliases' options. Now this information is printed
   with '--pkg-cstate-limit' option. This effectively reverts the corresponding
   change in v1.4.29.

## [1.4.31] - 2023-08-16
### Fixed
 - Fix 'pepc cstates config --cstates all' printing output.

## [1.4.30] - 2023-08-14
### Fixed
 - Prevent 'pepc pstates info' and 'pepc power info' from printing unsupported
   properties when no properties are specified.

## [1.4.29] - 2023-07-31
### Fixed
 - Fix typo in 'pepc' tool sub-option 'config/info's help text.
### Changed
 - Group propeties by source only when printing all properties. This
   partially reverts grouping introduced in version 1.4.28.
 - Change '--cstates' option output format, the properties are now
   grouped by their source.
 - Move "governors" from '--governor' option, to it own option '--governors'.
 - Move package C-state limit lock, limits and alises from option
   '--pkg-cstate-limit', to their own options: '--pkg-cstate-limit-lock',
   '--pkg-cstate-limits' and '--pkg-cstate-limit-aliases'.

## [1.4.28] - 2023-07-14
### Changed
 - Change 'info' sub-command output format, the properties are now
   grouped by their source.

## [1.4.27] - 2023-07-06
### Fixed
 - Fix crash intoduced in v1.4.26, which occurred when running 'pepc'
   commands on hybrid CPUs.

## [1.4.26] - 2023-07-06
### Fixed
 - Fix '--min-freq-hw' and '--max-freq-hw' options on hybrid CPUs.

## [1.4.25] - 2023-06-28
### Added
 - Add 'pepc topology --hybrid' option.

## [1.4.24] - 2023-06-23
### Changed
 - Improve error messages about unsupported features.
 - Add Niklas Neronin to project maintainers.

## [1.4.23] - 2023-06-16
### Changed
 - Minor changes to support 'wult' project.

## [1.4.22] - 2023-06-15
### Changed
 - Minor changes to support 'stats-collect' project.

## [1.4.21] - 2023-06-12
### Changed
 - Minor updates in self-tests.

## [1.4.20] - 2023-06-07
### Fixed
 - Fix scope for CStates properties 'cstate_prewake', 'c1e_autopromote'.
   The scope for these properties is die on Cascade Lake AP.

## [1.4.19] - 2023-05-30
### Fixed
 - Fix '--cstate-prewake' and '--c1e-autopromote' options scope: was "core",
   should be "package".

## [1.4.18] - 2023-05-25
### Added
 - Add '--override-cpu-model' option to 'pepc power/pstates/cstates'.
   This options can be used for overriding the CPU model.

## [1.4.17] - 2023-05-17
### Fixed
 - Add workaround for inconsistent CPU frequency driver behavior on AMD
   systems. This fixes 'pepc pstates config --max-freq max' failure on AMD
   systems.

## [1.4.16] - 2023-05-12
### Added
 - Add '--tdp' option to 'pepc power info', for reading CPU package TDP.
 - Add 'pepc power' manual page.
### Changed
 - Rename 'pepc power' options by removing the '-hw' part from them.
 - Install manual pages when using 'pip install'.

## [1.4.15] - 2023-05-03
### Added
 - New 'pepc power' command. Currently supports only RAPL package power.

## [1.4.14] - 2023-04-27
### Changed
 - Minor change related to process output parsing. Needed for the 'wult'
   project.

## [1.4.13] - 2023-04-21
### Added
 - Initial (may be not fully correct) Sierra Forest platform support.

## [1.4.12] - 2023-04-17
### Fixed
 - Fix Debian build dependency for pytests to run in build environment
   (take 2).

## [1.4.11] - 2023-04-17
### Fixed
 - Fix Debian build dependency for pytests to run in build environment.

## [1.4.10] - 2023-04-14
### Fixed
 - Fix a crash in RHEL, which has an empty newline in '/etc/release' - do not
   choke on it.

## [1.4.9] - 2023-04-11
### Fixed
 - Fix scope for PStates properties 'epb_hw', 'bus_clock' and CStates
   properties 'c1_demotion', 'c1_undemotion', 'pkg_cstate_limit'. The scope
   for these properties is different on different systems.
 - Fix scope for various MSR-based features, such as EPB, and C1 demotion:
   it is platform-dependent and was incorrect for some platforms
   (e.g., Knights Landing).
### Added
 - Add '--bus-clock' option to 'pepc pstates info' command.
 - Extend split_csv_line() in Trivial.py.

## [1.4.8] - 2023-03-19
### Fixed
 - Fixed Denverton and Snow Ridge package C-state limits.
### Changed
 - Split 'pepc' manual page on multiple per-command pages.
 - Improve manual pages.
 - Simplify '--help' output.

## [1.4.7] - 2023-03-16
### Changed
 - pepc cstates info: print C-state description in addition to latency and
   target residency.

## [1.4.6] - 2023-03-15
 - No user-visible changes. Technical release.

## [1.4.5] - 2023-03-15
 - No user-visible changes. Technical release.

## [1.4.4] - 2023-03-15
### Changed
 - Refine package C-states support for Granite Rapids Xeon.

## [1.4.3] - 2023-03-15
### Added
 - Add package C-states support for Granite Rapids Xeon.

## [1.4.2] - 2023-03-15
### Fixed
 - Fix errors handling regression introduced in v1.4.1.

## [1.4.1] - 2023-03-10
### Fixed
 - Fix 'pepc pstates' crash on old, pre-HWP systems.

## [1.4.0] - 2023-02-23
### Fixed
 - When reading unsupported MSRs 'pepc' tool will treat them as "not supported",
   instead of erroring.
### Changed
 - Column 'Die' is excluded from 'pepc pstates info' default columns, on one
   die per package systems.
 - Column 'Module' is excluded from 'pepc pstates info' default columns, on one
   core per module systems.

## [1.3.46] - 2023-02-06
### Fixed
 - Fix 'pepc [pc]states config' failure on systems that do not have the
   'systemct' tool installed (e.g., some Yocto-based systems).
### Added
 - Add '--core-siblings' option to all 'pepc' commands.
### Removed
 - Remove the '--ht-siblings' option of 'pepc cpu-hotplug offline'. The
   '--core-siblings' option should be used instead.

## [1.3.45] - 2023-02-03
### Added
 - Add partial Granite Rapids Xeon support.

## [1.3.44] - 2023-02-02
### Changed
 - Improve 'Systemctl' module to check if the 'systemctl' tool is installed.

## [1.3.43] - 2023-01-27
### Fixed
 - Fix 'pepc cstates config --pkg-cstate-limit' option, take 2. The fix in
   version 1.3.42 did not work in some cases.

## [1.3.42] - 2023-01-20
### Fixed
 - Fix 'pepc cstates config --pkg-cstate-limit' option, it did not work
   correctly in some cases because we made wrong assumptions about MSR scope.

## [1.3.41] - 2023-01-09
### Added
 - Add '-D'/'--dataset' option to 'pepc', it defines the dataset that will be
   used to emulate a host for running the command on.

## [1.3.40] - 2022-12-23
### Changed
 - Minor changes required for the 'wult' project.

## [1.3.39] - 2022-12-16
### Fixed
 - Fix 'pepc' crash on some system when it is run without arguments.

## [1.3.38] - 2022-12-16
### Fixed
 - Revert changes in 1.3.37 due to them breaking dependent projects.

## [1.3.37] - 2022-12-16
### Fixed
 - Fix 'pepc' crash on some system when it is run without arguments.

## [1.3.36] - 2022-12-15
### Fixed
 - Fix self-tests: they used real sysfs instead of emulated data in some cases.

## [1.3.35] - 2022-12-14
### Fixed
 - Fix regression introduced in 1.3.34: 'pepc cstates info' and
   'pepc pstates info' crashed with 'ValueError' in some cases.
 - Fix error when the '--epb' option is used on a system that does not support
   EPB.
### Added
 - Add Grand Ridge SoC support.
 - Add '--epb-hw' and '--epp-hw' options of 'pepc pstates', they can be used to
   access EPB/EPP via the MSR registers (instead of accessing via sysfs).
### Removed
 - Remove the '--epb-policy' and '--epp-policy' options of 'pepc pstates'. Now
   policy can be specified using the '--epb' and '--epp' options.
### Changed
 - Change '--epb' and '--epp' options of 'pepc pstates': use sysfs instead of
   MSR. Access via MSR is now done using the '--epb-hw' and '--epp-hw' options.

## [1.3.34] - 2022-12-09
### Fixed
 - pepc cstates: do not fail on systems that have no C-states.

## [1.3.33] - 2022-12-02
### Added
 - Add '--online-only' option to 'pepc topology info' command.
 - Add '--columns' option to 'pepc topology info' command.
 - Add 'module' level support to the 'CPUInfo.py' module.
 - Add Raptor and Meteor Lake support.
### Changed
 - Change 'pepc topology info' option '--order' to be case insensitive.

## [1.3.32] - 2022-11-29
### Fixed
 - Fix regression introduced in 1.3.29: 'pepc cstates config --pkg-cstate-limit'
   did not print anything on some systems.

## [1.3.31] - 2022-11-28
### Fixed
 - Fix regression introduced in 1.3.29: 'pepc cstates info --pkg-cstate-limit'
   did not print anything on some systems.
### Added
 - Add '--cpus', '--cores' and '--packages' options to 'pepc topology info'
   command.

## [1.3.30] - 2022-11-25
### Fixed
 - Fix regression introduced in 1.3.29: setting CPU frequency sometimes fails.

## [1.3.29] - 2022-11-23
### Fixed
 - Fix 'pepc pstates config/info --epp' option: it incorrectly assumed that EPP
   is per-package, even though it is per-CPU.
 - Fix kernel 'DEBUG_LOCKS_WARN_ON' warning caused by wult drivers.
### Added
 - Add 'pepc [pc]state info --yaml' option.
 - Add 'topology info' command that prints CPU topology information.
### Changed
 - Remove '--save' and '--restore' option, add 'pepc [pc]states save/restore'
   sub-commands instead.

## [1.3.28] - 2022-11-11
### Added
 - Add '--save' -option to 'pepc pstates info' and 'pepc cstates info' commands.
 - Add '--restore' -option to 'pepc pstates config' and 'pepc cstates config'
   commands.
 - Add Emerald Rapids support.

## [1.3.27] - 2022-11-07
### Added
 - Add options '--min-freq-hw' and '--max-freq-hw' to 'pepc pstate info' command.
 - pepc pstates: add "Pm" special frequency value support.

## [1.3.26] - 2022-11-02
### Changed
 - minor changes needed to support the 'wult' project.

## [1.3.25] - 2022-10-31
### Added
 - pepc pstates: add "P1" and "Pn" special frequency values support. Now they
   can be used with '--min-freq' and '--max-freq' options.
### Changed
 - pepc cpu-hotplug online/offline: rename the '--siblings' to '--ht-siblings'.

## [1.3.24] - 2022-10-28
### Added
 - Add the 'cstates config --intel-pstate-mode' option.

## [1.3.22] - 2022-10-12
### Fixed
 - Do not try to read HWP-related features (like EPP) on non-HWP systems.
### Added
 - Add and 'intel_pstate' driver operation mode support (passive, active).
### Changed
 - The "pepc [pc]state info" does not print information about unsupported
   commands any longer.

## [1.3.21] - 2022-09-29
### Fixed
 - Fix bugs in tests.
### Added
 - Add a couple of helper functions to the 'Trivial' module, they are needed
   for the dependent 'wult' project.

## [1.3.20] - 2022-09-21
### Added
 - Add scope awareness to the 'MSR.py' module. This speeds 'pepc' commands that
   end up accessing MSR registers which have, say, package scope.

## [1.3.19] - 2022-09-19
### Added
 - Alder Lake mobile support (CPU model 0xBE).

## [1.3.18] - 2022-09-16
### Changed
 - Another minor update in 'Exceptions.py' to satisfy 'wult' project needs.

## [1.3.17] - 2022-09-08
### Added
 - A minor update in 'Exceptions.py' to satisfy 'wult' project needs.

## [1.3.16] - 2022-09-07
### Added
 - Added OS package information for the 'libbpf' library.

## [1.3.15] - 2022-09-01
### Fixed
 - Fix ASPM-related tests failures when they run on real HW (vs emulated).
### Added
 - Add 'cstates config --governor' option.

## [1.3.14] - 2022-08-16
### Fixed
 - Fix 'cpu info --turbo' failure on turbo-less systems.

## [1.3.13] - 2022-08-10
### Added
 - Add Knights Landing/Mill package C-state limit table.

## [1.3.12] - 2022-08-01
### Added
 - Add idle driver and governor options to 'cstates info'.

## [1.3.11] - 2022-07-15
### Fixed
 - Changed Sapphire Rapids PC6 limits: support retention and non-retention
   variants.

## [1.3.10] - 2022-07-06
### Changed
 - Minor improvements required for RPM packaging.

## [1.3.9] - 2022-06-24
### Changed
 - Add RPM packaging support.

## [1.3.8] - 2022-06-09
### Changed
 - pepc: provide a python interpreter search capability dependent projects.

## [1.3.7] - 2022-06-03
### Changed
 - pepc: fix in 'abspath()', which fixes the 'wult' tool using pepc libraries.

## [1.3.6] - 2022-05-25
### Changed
 - pepc: fix running commands in Ubuntu/'dash' (regression in 1.3.5)

## [1.3.5] - 2022-05-25
### Changed
 - pepc: add per-property options to 'cstates info' and 'pstates info'.

## [1.3.4] - 2022-04-08
### Changed
 - pepc cstates config: fix "bad C-state name" failures.
 - pepc: improve error message if sub-command was not specified.

## [1.3.3] - 2022-04-08
### Changed
 - pepc cstates config --pkg-cstate-limit: fix failures on some systems.

## [1.3.2] - 2022-04-07
### Changed
 - pepc cstates config --epp <policy_name>: now fixed and works.
 - pepc: fix EPP support on Broadwell-based systems.

## [1.3.1] - 2022-03-22
### Changed
 - pepc: do not fail when used in 'dash'.
 - pepc: fix crash introduced in version 1.3.0.

## [1.3.0] - 2022-03-18
### Changed
 - pepc pstates: re-implemented.
 - pepc pstates: command-line options made consistent with 'pepc cstates'.
 - pepc cstates: added Alder Lake package C-state limits support.

## [1.2.4] - 2022-03-02
### Changed
 - pepc: fix 'pepc cstates config' crash in Ubuntu 20.04.3 LTS.

## [1.2.3] - 2022-02-19
### Changed
 - pepc: fix errors on remote systems not using 'intel_pstate' driver.

## [1.2.2] - 2022-02-18
### Changed
 - pepc: fix crash on systems for which there are no package C-states aliases.

## [1.2.1] - 2022-02-14
### Changed
 - pepc: fix case-sensitivity bugs.

## [1.2.0] - 2022-02-11
### Changed
 - Merge the 'cstate set' command into 'cstate config'.
 - Rename 'aspm set' command to 'aspm config'.
 - Improve C-states information printing.
 - Fixed '--cores' and '--packages' dependency for C-state commands.
 - Fix and improve CPU onlining/offlining.

## [1.1.4] - 2022-01-28
### Changed
 - pepc: fix file type markers in 'lsdir()', which fixes 'wult scan'.

## [1.1.3] - 2021-11-12
### Changed
 - pepc: python 3.8 crash fix.

## [1.1.2] - 2021-11-12
### Changed
 - pepc: speed-up the C-state validation, required for wult tool.

## [1.1.1] - 2021-11-03
### Changed
 - pepc: start tagging new releases, otherwise only very minor changes.

## [1.1.0] - 2021-10-29
### Changed
 - pepc: first release.