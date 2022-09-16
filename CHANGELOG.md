# Changelog

Changelog practices: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning practices: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.19] - ADD DATE HERE
### Fixed
### Added
### Removed
### Changed

## [1.3.18] - ADD DATE HERE
### Fixed
### Added
### Removed
### Changed
 - Another minor update in 'Exceptions.py' to satisfy 'wult' project needs.

## [1.3.17] - 2022-09-08
### Fixed
### Added
 - A minor update in 'Exceptions.py' to satisfy 'wult' project needs.
### Removed
### Changed

## [1.3.16] - 2022-09-07
### Fixed
### Added
 - Added OS package information for the 'libbpf' library.
### Removed
### Changed

## [1.3.15] - 2022-09-01
### Fixed
 - Fix ASPM-related tests failures when they run on real HW (vs emulated).
### Added
 - Add 'cstates config --governor' option.
### Removed
### Changed

## [1.3.14] - 2022-08-16
### Fixed
 - Fix 'cpu info --turbo' failure on turbo-less systems.
### Added
### Removed
### Changed

## [1.3.13] - 2022-08-10
### Fixed
### Added
 - Add Knights Landing/Mill package C-state limit table.
### Removed
### Changed

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
