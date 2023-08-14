# Changelog

Changelog practices: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning practices: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [ADD NEW VERSION HERE] - ADD DATE HERE
### Fixed
### Added
### Removed
### Changed

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
 - Initial (may be not fully correct) Sierra Forrest platform support.

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