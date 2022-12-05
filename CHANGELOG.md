# Changelog

Changelog practices: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning practices: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [ADD NEW VERSION HERE] - ADD DATE HERE
### Fixed
### Added
### Removed
 - Remove 'pepc pstates' option '--epb-policy'.
### Changed

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