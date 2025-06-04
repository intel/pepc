# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides the 'OpTarget' class, which represents the "target" of a pepc operation in
terms of what CPU, core, module, die, or package numbers the operation should read or modify.
"""

from pepclibs import CPUInfo
from pepclibs.helperlibs import Logging, LocalProcessManager, ClassHelpers, Trivial
from pepclibs.helperlibs.Exceptions import Error

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class ErrorNoTarget(Error):
    """No operation target was specified or found."""

class ErrorNoCPUTarget(Error):
    """
    The operation target was specified, but it does not include any CPUs (e.g., only I/O dies were
    specified).
    """

class OpTarget(ClassHelpers.SimpleCloseContext):
    """
    This class represents the "target" of a pepc operation in terms of what CPU, core, module, die,
    or package numbers the operation should read or modify.

    Public methods overview.
    * 'get_cpus()' - return the target CPU numbers as a list of integers.
    * 'get_dies()' - return the target die numbers as a dictionary.
    * 'get_packages()' - return the target CPU numbers as a list of integers.
    """

    def _get_cpus(self, exclude=None):
        """Implements 'get_cpus()'."""

        cpus = []
        if exclude is None:
            exclude = []

        in_cpus = self.cpus if "CPU" not in exclude else []
        in_cores = self.cores if "core" not in exclude else []
        in_core_siblings = self.core_siblings if "core" not in exclude else []
        in_modules = self.modules if "module" not in exclude else []
        in_module_siblings = self.module_siblings if "module" not in exclude else []
        in_dies = self.dies if "module" not in exclude else []
        in_packages = self.packages if "module" not in exclude else []

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

        # Because cores and dies numbers may be relative (as opposed to globally unique CPU and
        # package numbers), when either of them was specified, packages list is treated as
        # "package numbers for core or die numbers", not as input packages. If no cores or dies were
        # specified, packages list is treated independently, as input packages.
        if in_packages and not (self.cores or self.dies):
            cpus += self._cpuinfo.packages_to_cpus(packages=in_packages)

        if in_core_siblings:
            cpus = self._cpuinfo.select_core_siblings(cpus, in_core_siblings)
            # Handle the situation when both core an module siblings are targeted.
            if in_module_siblings:
                return self._cpuinfo.select_module_siblings(cpus, in_module_siblings)

        if in_module_siblings:
            return self._cpuinfo.select_module_siblings(cpus, in_module_siblings)

        return self._cpuinfo.normalize_cpus(cpus, offline_ok=self._offline_ok)

    def _only_io_dies(self):
        """
        Return 'True' if only I/O dies were specified as a target, return 'False' otherwise (no
        target dies at all, or some of the target dies are comput dies).
        """

        dies = self.get_dies()
        if not dies:
            return False

        for package, pkg_dies in dies.items():
            io_dies = self._cpuinfo.get_package_dies(package=package, compute_dies=False, io_dies=True)
            if not set(pkg_dies).issubset(set(io_dies)):
                return False

        return True

    def get_cpus(self):
        """
        Return list of target CPU numbers. Raise 'ErrorNoTarget' if no CPUs, cores, modules, dies,
        or packages were specified (i.e., there is no operation target at all). Raise
        'ErrorNoCPUTarget' if there is an operation target, but it does not include CPUs (e.g., only
        I/O dies were specified).
        """

        if "cpus" not in self._cache:
            self._cache["cpus"] = self._get_cpus()

        if len(self._cache["cpus"]) != 0:
            return self._cache["cpus"]

        if not self.dies:
            raise ErrorNoTarget("no CPU numbers were specified")

        # Supposedly only I/O dies were specified, and they do not have CPUs. Verify this
        # assumption, and if it is true, format a helpful error message.
        if not self._only_io_dies():
            raise ErrorNoTarget("BUG: failed to figure out CPU numbers")

        dies_str = self._cpuinfo.dies_to_str(self.get_dies())
        raise ErrorNoCPUTarget(f"no CPU numbers were specified.\n  The following I/O dies were "
                               f"specified, but they do not have CPUs: {dies_str}.")

    def get_dies(self, strict=True):
        """
        Return target die numbers. The arguments are as follows.
          * strict - if 'True', the operation must target only dies, otherwise the operation may
                     target any level below "die" as well (e.g., it may target die 4 and CPU 0).

        The die numbers are returned in form of a dictionary, with keys being integer package
        numbers and values being lists of integer die numbers in the package.

        In "strict" mode ('strict' is 'True'), if the operation target includes sub-levels of the
        "die" level (i.e., there are CPUs that do not comprise full die), the 'ErrorNoTarget'
        exception is raised.
        """

        if "dies" in self._cache:
            return self._cache["dies"]

        cpus = self._get_cpus(exclude=["die"])
        dies, rem_cpus = self._cpuinfo.cpus_div_dies(cpus)
        if strict and rem_cpus:
            human_cpus = Trivial.rangify(rem_cpus)
            raise ErrorNoTarget(f"the following CPUs do not comprise a die: {human_cpus}",
                                cpus=rem_cpus)

        if self.dies:
            for package, pkg_dies in self.dies.items():
                if package not in dies:
                    dies[package] = []
                dies[package] += pkg_dies
        elif not self.cpus and not self.cores and not self.modules and self.packages:
            # One or more packages are targeted. No specific CPUs, cores, or modules are targeted.
            # Assume this means that I/O dies are targeted too, so include them.
            for package in self.packages:
                if package not in dies:
                    dies[package] = []
                dies[package] += self._cpuinfo.get_package_dies(package=package)

        for package in dies:
            dies[package] = Trivial.list_dedup(dies[package])

        self._cache["dies"] = dies
        return self._cache["dies"]

    def get_packages(self, strict=True):
        """
        Return target die numbers as a list of integers. The arguments are as follows.
          * strict - if 'True', the operation must target only dies, otherwise the operation may
                     target any level below "die" as well (e.g., it may target die 4 and CPU 0).

        In "strict" mode ('strict' is 'True'), if the operation target includes sub-levels of the
        "die" level (i.e., there are CPUs that do not comprise full die), the 'ErrorNoTarget'
        exception is raised.
        """

        if "packages" in self._cache:
            return self._cache["packages"]

        cpus = self._get_cpus(exclude=["package"])
        packages, rem_cpus = self._cpuinfo.cpus_div_packages(cpus)
        if strict and rem_cpus:
            human_cpus = Trivial.rangify(rem_cpus)
            raise ErrorNoTarget(f"the following CPUs do not comprise a package: {human_cpus}",
                                cpus=rem_cpus)

        if self.packages:
            packages += self.packages
        self._cache["packages"] = Trivial.list_dedup(packages)
        return self._cache["packages"]

    def _parse_input_nums(self, nums, what=None):
        """
        Parse an '__init__()' input argument that includes a collection of numbers (such as CPU
        numbers). Return a list of integer numbers.
        """

        if nums == "all":
            return nums
        return Trivial.parse_int_list(nums, dedup=True, what=what)

    def _build_package_indexed_dict(self, nums, sname):
        """
        Handle the situation when '__init__()' is called with core and/or die numbers specified
        without package numbers. On some systems core and die numbers are relative to package
        numbers (as opposed to being globally unique), so there may be ambiguity (e.g., user
        specified die 0 without specifying package number, but there are two dies 0 in packages 0
        and 1). Check the user-provided core or die numbers ('nums') and if they are ambiguous,
        raise an exception. Otherwise, convert 'nums' into a dictionary indexed by package number
        and return the dictionary.
        """

        if sname not in ("die", "core"):
            raise Error("BUG: only die and core numbers may be relative to package numbers")

        pkg2nums = {}

        package_to_nums = getattr(self._cpuinfo, f"package_to_{sname}s")
        for package in self._cpuinfo.get_packages():
            pkg2nums[package] = package_to_nums(package)

        if nums != "all":
            # Verify that core/die numbers in 'nums' are valid: exist in at least one package.
            all_nums = set()
            for package, package_nums in pkg2nums.items():
                all_nums.update(package_nums)

            if not set(nums).issubset(all_nums):
                bad_nums = set(nums) - all_nums
                bad_nums = ",".join(str(num) for num in sorted(bad_nums))
                if len(pkg2nums) > 1:
                    pkg_str = " in any package"
                else:
                    pkg_str = ""
                raise Error(f"the following {sname} number(s) do not exist{pkg_str}: {bad_nums}")

        num2pkg = {}
        result = {}

        for package, package_nums in pkg2nums.items():
            for num in nums:
                if num not in package_nums:
                    continue

                if num not in num2pkg:
                    num2pkg[num] = package
                    if package not in result:
                        result[package] = []
                    result[package].append(num)
                    continue

                raise Error(f"ambiguous {sname} number {num}: there is {sname} {num} in "
                            f"packages {num2pkg[num]} and {package}.\n"
                            f"Please, specify package numbers as well, because {sname} numbers "
                            f"are not unique{self._pman.hostmsg}, they are relative to "
                            f"package.")

        return result

    def __init__(self, pman=None, cpuinfo=None, cpus=None, cores=None, modules=None, dies=None,
                 packages=None, core_siblings=None, module_siblings=None, offline_ok=False):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the target host.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * cpus - collection of integer CPU numbers.
          * cores - can be either a list or tuple (1) or a dictionary (2). In case of (1), it is a
                    collection of core numbers. Core numbers are relative to package numbers. If
                    'package' is not specified, 'cores' are assumed to be for package 0.  Otherwise
                    they are assumed to be for every package in 'packages'. In case of (2), it is a
                    dictionary with keys being integer package numbers and values being lists of
                    integer core number within the package (the key).
          * modules - collection of module numbers.
          * dies - can be either a list or tuple (1) or a dictionary (2). In case of (1), it is a
                   collection of die numbers. Die numbers may be relative to package numbers (but
                   this depends on the system and the kernel version - on some systems die numbers
                   are globally unique). If 'package' is not specified, 'dies' are assumed to be for
                   package 0. Otherwise they are assumed to be for every package in 'packages'. In
                   case of (2), it is a dictionary with keys being integer package numbers and
                   values being lists of integer die number within the package (the key).
          * packages - collection of package numbers.
          * core_siblings - collection of integer core sibling numbers. Will be used to reduce the
                            final list of CPUs using 'CPUInfo.select_core_siblings()'.
          * module_siblings - collection of integer module sibling numbers.
                              Will be used to reduce the final list of CPUs using
                              'CPUInfo.select_module_siblings()'.
          * offline_ok - if 'True', offline CPU numbers in 'cpus' are acceptable, otherwise they
                         will cause an exception.

        The cpu, core, module, die, package, core and module sibling numbers could be a list of
        integer or comma-separated string of integers.

        If no cpu, core, module, die, package, core and module sibling numbers were specified,
        assume that the following was specified:
          * cpus: "all"
          * packages: "all"
          * dies: "all"

        The following arguments may use the special "all" value:
          * cpus - to specify all CPUs.
          * cores - to specify all cores.
          * modules - to specify all modules.
          * dies - to specify all dies.
          * packages - to specify all packages.

        The terminology.

        1. Input CPUs/cores/etc.
          * Input CPUs: CPU numbers provided via the 'cpus' input argument.
          * Input cores: core numbers provided via the 'cores' input argument.
          * Input modules: module numbers provided via the 'modules' input argument.
          * Input dies: die numbers provided via the 'dies' input argument.
          * Input packages: package numbers provided via the 'packages' input argument.
        2. Target or targeted CPUs/cores/etc - best explained with an example, see below.

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

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._offline_ok = offline_ok

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None

        # Target CPU, core, module, die, and package numbers.
        self.cpus = None
        self.cores = None
        self.modules = None
        self.dies = None
        self.packages = None
        self.core_siblings = None
        self.core_sib_cpus = None
        self.module_siblings = None
        self.module_sib_cpus = None

        # The cached result of 'get_cpus()', 'get_dies()', and 'get_packages()'.
        self._cache = {}

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        if not cpus and not cores and not modules and not dies and not packages:
            # Nothing was provided. Assume everything in this case: all CPUs and all dies in order
            # to cover I/O dies.
            cpus = "all"
            dies = "all"
            packages = "all"

        if not packages and (dies or cores):
            # No package numbers were provided, but core ore die numbers were provided. Core and die
            # numbers are special because they may be relative, so they require package numbers. But
            # make one convenient exception: if no packages were provided, but all cores and/or dies
            # are requested, assume that all packages are requested.
            if dies == "all" or cores == "all":
                packages = "all"

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

        # Core and die numbers may be relative to the package number. Store them in a dictionary
        # indexed by the package number.
        #
        # Handle input core numbers.
        if cores:
            self.cores = {}
            if not isinstance(cores, dict):
                nums = self._parse_input_nums(cores, what="core numbers")
                if not packages:
                    self.cores = self._build_package_indexed_dict(nums, "core")
                else:
                    for pkg in pkgs:
                        self.cores[pkg] = self._cpuinfo.normalize_cores(nums, package=pkg)
            else:
                for pkg, pkg_cores in cores.items():
                    pkg = self._cpuinfo.normalize_package(pkg)
                    for core in pkg_cores:
                        core = self._cpuinfo.normalize_core(core, package=pkg)
                        if pkg not in self.cores:
                            self.cores[pkg] = []
                        if core not in self.cores[pkg]:
                            self.cores[pkg].append(core)

        # Handle input die numbers.
        if dies:
            self.dies = {}
            if not isinstance(dies, dict):
                nums = self._parse_input_nums(dies, what="die numbers")
                if not packages:
                    self.dies = self._build_package_indexed_dict(nums, "die")
                else:
                    for pkg in pkgs:
                        self.dies[pkg] = self._cpuinfo.normalize_dies(nums, package=pkg)
            else:
                for pkg, pkg_dies in dies.items():
                    pkg = self._cpuinfo.normalize_package(pkg)
                    for die in pkg_dies:
                        die = self._cpuinfo.normalize_die(die, package=pkg)
                        if pkg not in self.dies:
                            self.dies[pkg] = []
                        if die not in self.dies[pkg]:
                            self.dies[pkg].append(die)

        _cpus = None
        if core_siblings:
            self.core_siblings = self._parse_input_nums(core_siblings, what="core sibling numbers")
            _cpus = self._get_cpus()
            self.core_sib_cpus = self._cpuinfo.select_core_siblings(_cpus, self.core_siblings)

        if module_siblings:
            self.module_siblings = self._parse_input_nums(module_siblings,
                                                          what="module sibling numbers")
            _cpus = self._get_cpus()
            self.module_sib_cpus = self._cpuinfo.select_core_siblings(_cpus, self.module_siblings)

            if core_siblings:
                # Re-calculate core sibling CPUs taking into account the just initialized module
                # sibling CPUs.
                _cpus = self._get_cpus()
                self.core_sib_cpus = self._cpuinfo.select_core_siblings(_cpus, self.core_siblings)

        if _cpus is not None:
            self._cache["cpus"] = _cpus

        if _LOG.getEffectiveLevel() == Logging.DEBUG:
            if self.cpus:
                _LOG.debug("target CPUs: %s", Trivial.rangify(self.cpus))
            if self.cores:
                for pkg, nums in self.cores.items():
                    _LOG.debug("target package %d cores: %s", pkg, Trivial.rangify(self.cores))
            if self.modules:
                _LOG.debug("target modules: %s", Trivial.rangify(self.modules))
            if self.dies:
                for pkg, nums in self.dies.items():
                    _LOG.debug("target package %d dies: %s", pkg, Trivial.rangify(nums))
            if self.packages:
                _LOG.debug("target packages: %s", Trivial.rangify(self.packages))
            if self.core_siblings:
                _LOG.debug("target core sibling CPUs: %s", Trivial.rangify(self.core_sib_cpus))
            if self.module_siblings:
                _LOG.debug("target module sibling CPUs: %s", Trivial.rangify(self.module_sib_cpus))

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_cpuinfo", "_pman")
        ClassHelpers.close(self, close_attrs=close_attrs)
