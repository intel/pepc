# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide the 'OpTarget' class which represents the target of a pepc operation, specifying which CPUs,
cores, modules, dies, or packages are affected.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import CPUInfo
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import Literal, cast, TypedDict, Sequence, Union
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.CPUInfoTypes import AbsNumsType, RelNumsType, ScopeNameType

    class _CacheTypedDict(TypedDict, total=False):
        """
        Typed dictionary for the topology numbers cache.

        Args:
            cpus: Cached target CPU numbers.
            dies: Cached target die numbers.
            packages: Cached target package numbers.
        """

        cpus: list[int]
        dies: dict[int, list[int]]
        packages: list[int]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class ErrorNoTarget(Error):
    """No operation target was specified or found."""

class ErrorNoCPUTarget(Error):
    """
    The operation target was specified, but it does not include any CPUs (e.g., only non-compute
    dies were specified).
    """

class OpTarget(ClassHelpers.SimpleCloseContext):
    """
    A class for representing the target of a pepc operation, specifying which CPUs, cores, modules,
    dies, or packages are affected.

    This class provides flexible selection of CPU topology elements for operations, supporting both
    absolute and relative numbering (e.g., core/die numbers relative to package). It handles
    ambiguity, validates input, and supports targeting "all" elements or specific subsets.

    Public Methods:
        - get_cpus() - return the target CPU numbers.
        - get_dies() - return the target die numbers.
        - get_packages() - return the target package numbers.
        - close() - uninitialize the class object.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 cpus: AbsNumsType | str = (),
                 cores: AbsNumsType | RelNumsType | str = (),
                 modules: AbsNumsType | str = (),
                 dies: AbsNumsType | RelNumsType | str = (),
                 packages: AbsNumsType | str = (),
                 core_siblings: AbsNumsType | str = (),
                 module_siblings: AbsNumsType | str = (),
                 offline_ok: bool = False):
        """
        Initialize a class instance.

        Allow for flexible specification of CPU topology elements, supporting both absolute and
        relative numbering, as well as the special "all" value to target all available elements. If
        no topology arguments are provided, all CPUs, dies, and packages are selected by default.

        If no CPU, core, module, die, package, core and module sibling indices were specified,
        assume everything is targeted, i.e. the following is assumed:
        - cpus: "all"
        - packages: "all"
        - dies: "all"

        Args:
            pman: A process manager object representing the target host. If not provided, a local
                  process manager is used.
            cpuinfo: A CPU information object. If not provided, a new CPUInfo instance is created.
            cpus: Target CPU numbers. Accept a sequence of integers, a comma-separated string of CPU
                  numbers, or "all" to target all CPUs.
            cores: Target core numbers. Accept a sequence of integers, a mapping of package-indexed
                   core numbers, a comma-separated string of core numbers, or "all" to target all
                   cores. Core numbers are relative to package numbers on some systems (those
                   running older Linux kernel), and globally unique on others - both cases are
                   supported.
            modules: Target module numbers. Accept a sequence of integers, a comma-separated string
                     of module numbers, or "all" to target all modules.
            dies: Target die numbers. Accept a sequence of integers, a mapping of package-indexed
                  die numbers, a comma-separated string of die numbers, or "all" to target all
                  dies. Die numbers may be relative to package numbers on some systems (those
                  running older Linux kernel), and globally unique on others - both cases are
                  supported.
            packages: Target package numbers. Accept a sequence of integers, a comma-separated
                      string of package numbers, or "all" to target all packages.
            core_siblings: Core sibling indices to further filter CPUs. Accept a sequence of
                           integers or a comma-separated string of core sibling indices.
            module_siblings: Module sibling indices to further filter CPUs. Accept a sequence of
                             integers or a comma-separated string of module sibling indices.
            offline_ok: If True, offline CPUs in the selection are acceptable, if False, an
                        exception is raised for offline CPUs. This option is only relevant when
                        targeting specific CPU numbers via the 'cpus' argument. If 'cpus' is not
                        specified, this option is ignored and only online CPUs will be selected.

        Attributes:
            cpus: Input CPU numbers.
            cores: Input core numbers, indexed by package numbers.
            modules: Input module numbers.
            dies: Input die numbers, indexed by package numbers.
            packages: Input package numbers.
            core_siblings: Input core sibling indices.
            core_sib_cpus: CPUs selected by core sibling indices.
            module_siblings: Input module sibling indices.
            module_sib_cpus: CPUs selected by module sibling indices.

        Notes:
          - Terminology:
              * Input CPUs: CPU numbers provided via the 'cpus' input argument.
              * Input cores: core numbers provided via the 'cores' input argument.
              * Input modules: module numbers provided via the 'modules' input argument.
              * Input dies: die numbers provided via the 'dies' input argument.
              * Input packages: package numbers provided via the 'packages' input argument.
          - Target or targeted CPUs/cores/etc - the specific CPUs/cores/etc that are selected for an
            operation based on the input arguments.

        Raises:
            ErrorNoTarget: If no operation target is specified or found.
            ErrorNoCPUTarget: If the operation target does not include any CPUs (e.g., only
                              non-compute dies are specified).

        Examples:
            Consider a hypothetical system with the following topology.
              * Two packages: 0 and 1.
              * Each package has two dies: 0 and 1.
              * Each die has two CPUs.

            Here is the topology table.

            Package Die CPU
            ---------------
            0       0   0
            0       0   1
            0       1   2
            0       1   3
            1       0   4
            1       0   5
            1       1   6
            1       1   7

            A. If this class was instantiated with 'cpus="all"', then:
                 * it targets all CPUs
                 * it targets all dies
                 * it targets all packages
            B. If this class was instantiated with 'cpus="0-3"', then:
                 * it targets CPUs 0-3
                 * it targets dies 0,1 of package 0
                 * it targets package 0
            C. If this class was instantiated with 'cpus="0,1"', then:
                 * it targets CPUs 0,1
                 * it targets die 0 of package 0
                 * it targets no packages
            D. If this class was instantiated with 'cpus="0"', then:
                 * it targets CPU 0
                 * it targets no dies
                 * it targets no packages
            E. If this class was instantiated with 'packages="0"', then:
                 * it targets CPUs 0-4
                 * it targets dies 0,1 of package 0
                 * it targets package 0
            F. If this class was instantiated with 'packages="0", cpus="6"', then:
                 * it targets CPUs 0-4,6
                 * it targets no dies
                 * it targets no packages
            G. If this class was instantiated with 'packages="0", cpus="6,7"', then:
                 * it targets CPUs 0-4,6,7
                 * it targets no dies 0,1 of package 0 and die 1 of package 1
                 * it targets no packages
        """

        _LOG.debug(f"Initializing the '{self.__class__.__name__}' class object, input arguments: "
                   f"cpus={cpus!r}, cores={cores!r}, modules={modules!r}, dies={dies!r}, "
                   f"packages={packages!r}, core_siblings={core_siblings!r}, "
                   f"module_siblings={module_siblings!r}, offline_ok={offline_ok})")

        self._offline_ok = offline_ok

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        # The input CPU, core, module, die, and package numbers.
        self.cpus: AbsNumsType = []
        self.cores: RelNumsType = {}
        self.modules: AbsNumsType = []
        self.dies: RelNumsType = {}
        self.packages: AbsNumsType = []
        self.core_siblings: AbsNumsType = []
        self.core_sib_cpus: AbsNumsType = []
        self.module_siblings: AbsNumsType = []
        self.module_sib_cpus: AbsNumsType = []

        # The cached result of 'get_cpus()', 'get_dies()', and 'get_packages()'.
        self._cache: _CacheTypedDict = {}

        if pman:
            self._pman = pman
        else:
            self._pman = LocalProcessManager.LocalProcessManager()

        if cpuinfo:
            self._cpuinfo = cpuinfo
        else:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        if not cpus and not cores and not modules and not dies and not packages:
            # No input topology numbers were provided. Select all CPUs, dies, and packages by
            # default, ensuring non-compute dies are included as well.
            cpus = "all"
            dies = "all"
            packages = "all"

        if not packages and (dies or cores):
            # Input packages were not specified, but input cores or dies were specified. Since core
            # and die numbers can be relative to package numbers, explicit package selection is
            # normally required. However, for convenience, if all cores and/or dies are requested
            # ("all"), and no packages are specified, assume all packages are targeted.
            if dies == "all" or cores == "all":
                packages = "all"

        nums: AbsNumsType | Literal["all"]
        pkgs: AbsNumsType | Literal["all"]

        if cpus:
            nums = self._parse_input_nums(cpus, what="CPU numbers")
            self.cpus = self._cpuinfo.normalize_cpus(nums, offline_ok=offline_ok)
        if modules:
            nums = self._parse_input_nums(modules, what="module numbers")
            self.modules = self._cpuinfo.normalize_modules(nums)
        if packages:
            nums = self._parse_input_nums(packages, what="package numbers")
            pkgs = self.packages = self._cpuinfo.normalize_packages(nums)
        else:
            pkgs = (0,)

        # Handle input core numbers.
        if cores:
            self.cores = {}
            if not isinstance(cores, dict):
                if typing.TYPE_CHECKING:
                    _cores = cast(AbsNumsType | str, cores)
                else:
                    _cores = cores
                nums = self._parse_input_nums(_cores, what="core numbers")
                if not packages:
                    self.cores = self._build_package_indexed_dict(nums, "core")
                else:
                    for pkg in pkgs:
                        self.cores[pkg] = self._cpuinfo.normalize_package_cores(nums, package=pkg)
            else:
                if typing.TYPE_CHECKING:
                    self_cores = cast(dict[int, list[int]], self.cores)
                else:
                    self_cores = self.cores
                for pkg, pkg_cores in cores.items():
                    pkg = self._cpuinfo.normalize_package(pkg)
                    if pkg not in self_cores:
                        self_cores[pkg] = []
                    for core in pkg_cores:
                        core = self._cpuinfo.normalize_core(core, package=pkg)
                        self_cores[pkg].append(core)
                for pkg in self_cores:
                    self_cores[pkg] = Trivial.list_dedup(self_cores[pkg])
                self.cores = self_cores

        # Handle input die numbers.
        if dies:
            self.dies = {}
            if not isinstance(dies, dict):
                if typing.TYPE_CHECKING:
                    input_dies = cast(AbsNumsType | str, dies)
                else:
                    input_dies = dies
                nums = self._parse_input_nums(input_dies, what="die numbers")
                if not packages:
                    self.dies = self._build_package_indexed_dict(nums, "die")
                else:
                    for pkg in pkgs:
                        self.dies[pkg] = self._cpuinfo.normalize_package_dies(nums, package=pkg)
            else:
                if typing.TYPE_CHECKING:
                    self_dies = cast(dict[int, list[int]], self.dies)
                else:
                    self_dies = self.dies
                for pkg, pkg_dies in dies.items():
                    pkg = self._cpuinfo.normalize_package(pkg)
                    if pkg not in self_dies:
                        self_dies[pkg] = []
                    for die in pkg_dies:
                        die = self._cpuinfo.normalize_package_die(die, package=pkg)
                        self_dies[pkg].append(die)
                for pkg in self_dies:
                    self_dies[pkg] = Trivial.list_dedup(self_dies[pkg])
                self.dies = self_dies

        _cpus = self._get_cpus()
        if core_siblings:
            self.core_siblings = Trivial.parse_int_list(core_siblings, dedup=True,
                                                        what="core sibling indices")
            self.core_sib_cpus = self._cpuinfo.select_core_siblings(_cpus, self.core_siblings)

        if module_siblings:
            self.module_siblings = Trivial.parse_int_list(module_siblings, dedup=True,
                                                          what="module sibling indices")
            self.module_sib_cpus = self._cpuinfo.select_module_siblings(_cpus, self.module_siblings)

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if self.cpus:
                _LOG.debug("Target CPUs: %s", Trivial.rangify(self.cpus))
            if self.cores:
                for pkg, nums in self.cores.items():
                    _LOG.debug("Target package %d cores: %s", pkg, Trivial.rangify(nums))
            if self.modules:
                _LOG.debug("Target modules: %s", Trivial.rangify(self.modules))
            if self.dies:
                for pkg, nums in self.dies.items():
                    _LOG.debug("Target package %d dies: %s", pkg, Trivial.rangify(nums))
            if self.packages:
                _LOG.debug("Target packages: %s", Trivial.rangify(self.packages))
            if self.core_siblings:
                _LOG.debug("Target core sibling CPUs: %s", Trivial.rangify(self.core_sib_cpus))
            if self.module_siblings:
                _LOG.debug("Target module sibling CPUs: %s", Trivial.rangify(self.module_sib_cpus))

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _parse_input_nums(self, nums: AbsNumsType | str,
                          what: str = "") -> list[int] | Literal["all"]:
        """
        Parse an input topology argument (e.g., input CPUs).

        Args:
            nums: An input topology argument to parse.
            what: A string describing what 'nums' are (e.g., "CPU numbers"). Used in error messages.

        Returns:
            A list of integer numbers, or "all" if all elements are requested ('nums' is "all").

        Example:
            Parse "0,1,2" as [0, 1, 2].
        """

        if nums == "all":
            return "all"
        return Trivial.parse_int_list(nums, dedup=True, what=what)

    def _build_package_indexed_dict(self,
                                    nums: list[int] | Literal["all"],
                                    sname: Literal["core", "die"]) -> dict[int, list[int]]:
        """
        Build a dictionary mapping package numbers to specified core or die numbers.

        This method handles cases where core or die numbers are provided without package numbers.
        On some systems, core and die numbers are relative to package numbers and may not be
        globally unique (happens with older kernel versions, newer kernels have globally unique
        core and die numbers). If ambiguity is detected (e.g., the same core or die number exists in
        multiple packages), raise an exception. Otherwise, return a dictionary indexed by package
        number containing the specified core or die numbers.

        Args:
            nums: Core or die numbers to select, or "all" to select all available cores or dies.
            sname: Scope name, must be either "core" or "die".

        Returns:
            Dictionary mapping package numbers to lists of core or die numbers.
        """

        if sname not in ("die", "core"):
            raise Error("BUG: Only die and core numbers may be relative to package numbers")

        pkg2nums = {}

        if sname == "core":
            for package in self._cpuinfo.get_packages():
                pkg2nums[package] = self._cpuinfo.package_to_cores(package)
        else:
            for package in self._cpuinfo.get_packages():
                pkg2nums[package] = self._cpuinfo.get_package_dies(package=package,
                                                                   noncomp_dies=True)

        all_nums = set()
        for package, package_nums in pkg2nums.items():
            all_nums.update(package_nums)

        in_nums: list[int]
        if nums != "all":
            in_nums = nums
        else:
            in_nums = sorted(list(all_nums))

        # Verify that core/die numbers in 'in_nums' are valid: exist in at least one package.
        if not set(in_nums).issubset(all_nums):
            bad_nums = set(in_nums) - all_nums
            bad_nums_str = ",".join(str(num) for num in sorted(bad_nums))
            if len(pkg2nums) > 1:
                pkg_str = " in any package"
            else:
                pkg_str = ""
            raise Error(f"The following {sname} number(s) do not exist{pkg_str}: "
                        f"{bad_nums_str}")

        num2pkg: dict[int, int] = {}
        result: dict[int, list[int]] = {}

        for package, package_nums in pkg2nums.items():
            for num in in_nums:
                if num not in package_nums:
                    continue

                if num not in num2pkg:
                    num2pkg[num] = package
                    if package not in result:
                        result[package] = []
                    result[package].append(num)
                    continue

                raise Error(f"Ambiguous {sname} number {num}: there is {sname} {num} in packages "
                            f"{num2pkg[num]} and {package}.\nSpecify package numbers as well, "
                            f"because {sname} numbers are not unique{self._pman.hostmsg}, they "
                            f"are relative to package.")

        return result

    def _get_cpus(self,
                  exclude: Union[set[ScopeNameType], Sequence[ScopeNameType]] = ()) -> list[int]:
        """
        Retrieve target CPU numbers.

        Args:
            exclude: Scope names to exclude from the target selection.

        Raises:
            ErrorNoTarget: If no CPUs, cores, modules, dies, or packages were specified,
                           indicating that there is no operation target at all.
            ErrorNoCPUTarget: If an operation target exists, but it does not include CPUs
                              (e.g., only non-compute dies were specified).

        Returns:
            List of target CPU numbers.
        """

        cpus: list[int] = []

        in_cpus = self.cpus if "CPU" not in exclude else []
        in_cores = self.cores if "core" not in exclude else {}
        in_core_siblings = self.core_siblings if "core" not in exclude else []
        in_modules = self.modules if "module" not in exclude else []
        in_module_siblings = self.module_siblings if "module" not in exclude else []
        in_dies = self.dies if "die" not in exclude else {}
        in_packages = self.packages if "package" not in exclude else []

        if in_cpus:
            cpus += in_cpus

        if in_cores:
            for pkg, cores in in_cores.items():
                cpus += self._cpuinfo.cores_to_cpus(cores=cores, packages=(pkg,))

        if in_modules:
            cpus += self._cpuinfo.modules_to_cpus(modules=in_modules)

        if in_dies:
            for pkg, dies in in_dies.items():
                cpus += self._cpuinfo.dies_to_cpus(dies=dies, packages=(pkg,))

        # Core and die numbers may be relative to package numbers (unlike globally unique CPU and
        # package numbers). Therefore, when cores or dies are specified, the packages list is
        # interpreted as "packages for the specified cores or dies," rather than as standalone
        # input packages. If neither cores nor dies are specified, the packages list is treated
        # as standalone, representing the full set of targeted packages.
        if in_packages and not (self.cores or self.dies):
            cpus += self._cpuinfo.packages_to_cpus(packages=in_packages)

        if in_core_siblings:
            cpus = self._cpuinfo.select_core_siblings(cpus, in_core_siblings)
            # Handle the situation when both core and module siblings are targeted.
            if in_module_siblings:
                return self._cpuinfo.select_module_siblings(cpus, in_module_siblings)

        if in_module_siblings:
            return self._cpuinfo.select_module_siblings(cpus, in_module_siblings)

        return self._cpuinfo.normalize_cpus(cpus, offline_ok=self._offline_ok)

    def _only_noncomp_dies(self) -> bool:
        """
        Determine if the selection includes only non-compute dies.

        Returns:
            True if all target dies are non-compute dies, False otherwise.
        """

        dies = self.get_dies()
        if not dies:
            return False

        for package, pkg_dies in dies.items():
            noncomp_dies = self._cpuinfo.get_package_dies(package=package, compute_dies=False,
                                                          noncomp_dies=True)
            if not set(pkg_dies).issubset(set(noncomp_dies)):
                return False

        return True

    def get_cpus(self) -> list[int]:
        """
        Retrieve target CPU numbers.

        Raises:
            ErrorNoTarget: If no CPUs, cores, modules, dies, or packages were specified,
                           indicating that there is no operation target at all.
            ErrorNoCPUTarget: If an operation target exists, but it does not include CPUs
                              (e.g., only non-compute dies were specified).

        Returns:
            List of target CPU numbers.
        """

        if "cpus" not in self._cache:
            self._cache["cpus"] = self._get_cpus()

        if len(self._cache["cpus"]) != 0:
            return self._cache["cpus"]

        if not self.dies:
            raise ErrorNoTarget("No CPU numbers were specified")

        # It appears that only non-compute dies were specified, and they do not have any CPUs.
        # Confirm this assumption, and if correct, provide a clear error message.
        if not self._only_noncomp_dies():
            raise ErrorNoTarget("BUG: Failed to figure out CPU numbers")

        dies_str = self._cpuinfo.dies_to_str(self.get_dies())
        raise ErrorNoCPUTarget(f"No CPU numbers were specified.\n  The following non-compute dies "
                               f"were selected, but they do not have CPUs: {dies_str}.")

    def get_dies(self, strict: bool = True) -> dict[int, list[int]]:
        """
        Retrieve target die numbers.

        In strict mode, ensure that only dies are targeted. Raise 'ErrorNoTarget' exception if any
        CPUs do not comprise a full die. Otherwise, allow targeting of any level below "die".

        Args:
            strict: If True, require that only dies are targeted. If False, allow topology levels
                    below die.

        Returns:
            Dictionary where keys are package numbers and values are lists of die numbers.

        Raises:
            ErrorNoTarget: If 'strict' is True and some CPUs do not comprise a full die.
        """

        if "dies" in self._cache:
            return self._cache["dies"]

        cpus = self._get_cpus(exclude=["die"])
        dies, rem_cpus = self._cpuinfo.cpus_div_dies(cpus)
        if strict and rem_cpus:
            human_cpus = Trivial.rangify(rem_cpus)
            raise ErrorNoTarget(f"The following CPUs do not comprise a die: {human_cpus}",
                                cpus=rem_cpus)

        if self.dies:
            for package, pkg_dies in self.dies.items():
                if package not in dies:
                    dies[package] = []
                dies[package] += pkg_dies
        elif not self.cpus and not self.cores and not self.modules and self.packages:
            # One or more packages are targeted. No specific CPUs, cores, or modules are targeted.
            # Assume this means that non-compute dies are targeted too, so include them.
            for package in self.packages:
                if package not in dies:
                    dies[package] = []
                dies[package] += self._cpuinfo.get_package_dies(package=package, noncomp_dies=True)

        for package in dies:
            dies[package] = Trivial.list_dedup(dies[package])

        self._cache["dies"] = dies
        return self._cache["dies"]

    def get_packages(self, strict: bool = True) -> list[int]:
        """
        Retrieve target package numbers.

        In strict mode, ensure that only full packages are targeted. If any CPUs do not comprise a
        full package, raise 'ErrorNoTarget'.

        Args:
            strict: If True, require that the operation targets only full packages. If False, allow
                    targeting any level below "package".

        Returns:
            List of target package numbers.

        Raises:
            ErrorNoTarget: If strict is True and some CPUs do not comprise a full package.
        """

        if "packages" in self._cache:
            return self._cache["packages"]

        cpus = self._get_cpus(exclude=["package"])
        packages, rem_cpus = self._cpuinfo.cpus_div_packages(cpus)
        if strict and rem_cpus:
            human_cpus = Trivial.rangify(rem_cpus)
            raise ErrorNoTarget(f"The following CPUs do not comprise a package: {human_cpus}",
                                cpus=rem_cpus)

        if self.packages:
            packages += self.packages
        self._cache["packages"] = Trivial.list_dedup(packages)
        return self._cache["packages"]
