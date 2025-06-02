# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module provides API for printing properties.
"""

import sys
from pepctool import _PepcCommon
from pepclibs import CStates, CPUInfo
from pepclibs.helperlibs import Logging, ClassHelpers, Human, YAML, Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class _PropsPrinter(ClassHelpers.SimpleCloseContext):
    """The base class for printing properties."""

    def _print(self, msg):
        """Print message 'msg'."""

        if self._fobj:
            self._fobj.write(msg)
        else:
            _LOG.info(msg)

    def _fmt_cpus(self, cpus):
        """Format and return a string describing CPU numbers in the 'cpus' list."""

        cpus_range = Trivial.rangify(cpus)
        if len(cpus) == 1:
            return f"CPU {cpus_range}"

        allcpus = self._cpuinfo.get_cpus()
        if set(cpus) == set(allcpus):
            return "all CPUs"

        msg = f"CPUs {cpus_range}"
        pkgs, rem_cpus = self._cpuinfo.cpus_div_packages(cpus)
        if pkgs and not rem_cpus:
            # CPUs in 'cpus' are actually the packages in 'pkgs'.
            pkgs_range = Trivial.rangify(pkgs)
            if len(pkgs) == 1:
                msg += f" (package {pkgs_range})"
            else:
                msg += f" (packages {pkgs_range})"

        if self._cpuinfo.info["hybrid"]:
            hybrid_info = self._cpuinfo.get_hybrid_cpus()
            if len(hybrid_info) > 1:
                for htype, hcpus in hybrid_info.items():
                    if set(cpus) == set(hcpus):
                        hname = CPUInfo.HYBRID_TYPE_INFO[htype]["name"]
                        if len(cpus) == 1:
                            msg += f" ({hname})"
                        else:
                            msg += f" ({hname}s)"
                        break
        return msg

    def _fmt_packages(self, packages):
        """Format and return a string describing package numbers in the 'packages' list."""

        allpkgs = self._cpuinfo.get_packages()
        if set(packages) == set(allpkgs):
            if len(allpkgs) == 1:
                return "all CPUs"
            return "all packages"

        pkgs_range = Trivial.rangify(packages)
        if len(packages) == 1:
            return f"package {pkgs_range}"
        return f"packages {pkgs_range}"

    def _fmt_dies(self, pkgs_dies):
        """Format and return a string describing die numbers in the 'dies' dictionary."""

        # Special case: provide a simpler and easier to read message when dealing with all
        # dies in all packages.
        all_dies_all_packages = True
        for pkg, dies in pkgs_dies.items():
            if len(dies) != self._cpuinfo.get_dies_count(package=pkg):
                all_dies_all_packages = False

        packages_count = self._cpuinfo.get_packages_count()
        if all_dies_all_packages and len(pkgs_dies) == packages_count:
            if packages_count == 1:
                return "all CPUs"
            return "all dies in all packages"

        # Format the detailed string. Examples:
        #   * all dies of package 0, dies 1,2 of package 1.
        #   * die 1 of package 0, dies 0-3 of package 1.
        result = []
        for pkg, dies in pkgs_dies.items():
            if len(dies) == self._cpuinfo.get_dies_count(package=pkg):
                dies_str = "all dies"
            else:
                dies_str = Trivial.rangify(dies)
                if len(dies) == 1:
                    plural = ""
                else:
                    plural = "s"
                dies_str = f"die{plural} {dies_str}"

            result.append(f"{dies_str} in package {pkg}")

        return ", ".join(result)

    def _fmt_nums(self, sname, nums):
        """
        Formats and returns a string describing CPU, die, or package numbers in the 'nums' list (CPU
        or package case) or dictionary (die case)
        """

        if sname == "CPU":
            return self._fmt_cpus(nums)
        if sname == "package":
            return self._fmt_packages(nums)
        if sname == "die":
            # Use package formatting if there is only one die per package.
            if self._cpuinfo.get_dies_count(package=0) == 1:
                return self._fmt_packages(nums)
            return self._fmt_dies(nums)

        raise Error(f"BUG: unexpected scope name {sname} for message formatting")

    def _format_value_human(self, _, prop, val):
        """Format value 'val' of property described by 'prop' into the "human" format."""

        def _detect_progression(vals, min_len):
            """
            Detect if list of numbers 'vals' is an arithmetic progression, return the step if it is,
            and 'None' otherwise.
            """

            if len(vals) < min_len:
                return None

            step = vals[1] - vals[0]
            for idx, val in enumerate(vals[:-1]):
                if vals[idx + 1] - val != step:
                    return None
            return step

        def _format_unit(val, unit):
            """Format values with unit."""

            if unit:
                if unit == "s" and val > 100:
                    # Avoid kiloseconds and the like.
                    if Trivial.is_int(val):
                        return f"{int(val)}s"
                    return f"{val:.2f}s"
                return Human.num2si(val, unit=unit, decp=2)
            return str(val)

        unit = prop.get("unit")

        if prop["type"] in ("str", "bool"):
            return val

        if prop["type"] in ("int", "float"):
            return _format_unit(val, unit)

        if prop["type"].startswith("dict["):
            val = ", ".join(f"{k}={_format_unit(v, unit)}" for k, v in val)
        elif prop["type"] == "list[str]":
            val = ", ".join([_format_unit(v, unit) for v in val])
        elif prop["type"] in ("list[int]", "list[float]"):
            step = _detect_progression(val, 4)
            tar = False

            if len(val) == 1:
                val = _format_unit(val[0], unit)
            elif not step and len(val) > 1:
                # The frequency numbers are expected to be sorted in the ascending order. The last
                # frequency number is often the Turbo Activation Ration (TAR) - a value just
                # slightly higher than the base frequency to activate turbo. Detect this situation
                # and use concise notation for it too.
                step = _detect_progression(val[:-1], 3)
                if not step:
                    val = ", ".join([_format_unit(v, unit) for v in val])
                else:
                    tar = True

            if step:
                # This is an arithmetic progression, use concise notation.
                first = _format_unit(val[0], unit)
                if tar:
                    last = _format_unit(val[-2], unit)
                    tar = _format_unit(val[-1], unit)
                else:
                    last = _format_unit(val[-1], unit)
                    tar = None

                step = _format_unit(step, unit)
                val = f"{first} - {last} with step {step}"
                if tar:
                    val += f", {tar}"
        else:
            raise Error(f"BUG: property {prop['name']} as unsupported type '{prop['type']}")

        return val

    def _print_prop_human(self, pname, prop, sname, val, nums, action=None, prefix=None):
        """
        Format and print a message about property 'prop' and its value 'val' in the "human" format.
        The arguments are as follows.
          * pname - name of the property to print.
          * prop - the property information dictionary (for the property to print).
          * sname - scope name corresponding to the API that was used for reading the property. Can
                    be "die", "package", or "CPU" at the moment. Note, there is also
                    'prop["sname"]', and this is the functional scope of the property, but it does
                    not have to have the same value as 'sname'. For example, a property with "core"
                    scope ('prop["sname"] == "core"') could have been read using the per-CPU API, so
                    'sname' will be "CPU".
          * nums - a list defining the CPU or package numbers where the property has value 'val'.
                   But if 'sname' is "die", 'nums" is a dictionary with keys being package numbers
                   and values being lists of die numbers within the package (the key).
          * val - the value of property 'prop["name"]' on CPUs/dies/packages defined by 'num'.
          * action - same as in 'print_props()'.
          * prefix - a string to print before the property value message. This method prints a singe
                     line, and 'prefix' is the string to prefix the line with.
        """

        if nums is None or prop["sname"] == "global":
            # If there are no CPU/die/package numbers or this is a global property, just do not
            # print any of the numbers.
            sfx = ""
        else:
            nums = self._fmt_nums(sname, nums)
            sfx = f" for {nums}"

        msg = f"{prop['name']}: "

        if prefix is not None:
            msg = prefix + msg

        if val is None:
            val = "not supported"
        else:
            val = self._format_value_human(pname, prop, val)
            if val == "" and (prop["type"].startswith("list") or prop["type"].startswith("dict")):
                # The list or dictionary is empty. Just do not print the line at all.
                return

            if sfx and prop["type"] not in {"int", "float", "list[int]", "list[float]"}:
                val = f"'{val}'"

        if action is not None:
            msg += f"{action} "

        msg += f"{val}{sfx}"
        self._print(msg)

    def _do_print_aggr_pinfo_human(self, aggr_pinfo, action=None, prefix=None):
        """A helper for '_print_aggr_pinfo_human()' implementing the printing part."""

        props = self._pobj.props

        printed = 0
        for pname, pinfo in aggr_pinfo.items():
            for val, nums, in pinfo["vals"].items():
                self._print_prop_human(pname, props[pname], pinfo["sname"], val, nums=nums,
                                       action=action, prefix=prefix)
                printed += 1

        return printed

    def _print_aggr_pinfo_human(self, aggr_pinfo, group=False, action=None):
        """
        Print properties in the "human" format. The arguments are as follows.
          * aggr_pinfo - the aggregate properties information dictionary.
          * group - same as in 'print_props()'.
          * action - same as in 'print_props()'.
        """

        if group:
            prefix = " - "
        else:
            prefix = None

        printed = 0
        for mname, pinfo in aggr_pinfo.items():
            if group:
                self._print(f"Source: {self._pobj.get_mechanism_descr(mname)}")
            printed += self._do_print_aggr_pinfo_human(pinfo, action=action, prefix=prefix)
        return printed

    def _yaml_dump(self, info):
        """Dump dictionary 'info' in YAML format."""

        fobj = self._fobj
        if not fobj:
            fobj = sys.stdout

        YAML.dump(info, fobj)

    def _print_aggr_pinfo_yaml(self, aggr_pinfo):
        """Print the aggregate properties information in YAML format."""

        yaml_pinfo = {}

        for pinfo in aggr_pinfo.values():
            for pname, pinfo in pinfo.items():
                sname = pinfo["sname"]
                for val, nums in pinfo["vals"].items():
                    if val is None:
                        val = "not supported"

                    if pname not in yaml_pinfo:
                        yaml_pinfo[pname] = []

                    prop = self._pobj.props[pname]
                    if prop["type"].startswith("list["):
                        val = list(val)
                    if prop["type"].startswith("dict["):
                        val = dict(val)

                    if sname != "die":
                        nums_range = Trivial.rangify(nums)
                    else:
                        nums_range = {}
                        for pkg, dies in nums.items():
                            nums_range[pkg] = Trivial.rangify(dies)

                    yaml_pinfo[pname].append({"value" : val, sname: nums_range})

        self._yaml_dump(yaml_pinfo)
        return len(yaml_pinfo)

    @staticmethod
    def _get_pvinfo_num(pvinfo):
        """
        Return CPU, die, or package number and the level name from 'pvinfo' (property value info).
        """

        if "cpu" in pvinfo:
            return "CPU", pvinfo["cpu"]
        if "die" in pvinfo:
            return "die", (pvinfo["package"], pvinfo["die"])
        if "package" in pvinfo:
            return "package", pvinfo["package"]

        raise Error("BUG: bad property value dictionary, no 'cpu', 'die', or 'package' key found\n"
                    "The dictionary: {pvinfo}")

    def _build_aggr_pinfo_pname(self, pname, optar, mnames, skip_unsupported, override_sname=None):
        """Implement '_build_aggr_pinfo()' for one property."""

        prop = self._pobj.props[pname]
        apinfo = {}

        for pvinfo in _PepcCommon.get_prop_sname(self._pobj, pname, optar, mnames,
                                                 override_sname=override_sname):
            sname, num = self._get_pvinfo_num(pvinfo)
            val = pvinfo["val"]
            mname = pvinfo["mname"]

            if skip_unsupported and val is None:
                continue

            # Dictionary keys must be of an immutable type (python language requirement). Turn lists
            # and dictionaries into tuples.
            if prop["type"].startswith("list["):
                if val is not None:
                    val = tuple(val)
            if prop["type"].startswith("dict["):
                if val is not None:
                    val = tuple((k, v) for k, v in val.items())

            if sname == "die":
                package, die = num
            else:
                package, die = None, None

            if mname not in apinfo:
                apinfo[mname] = {}
            if pname not in apinfo[mname]:
                apinfo[mname][pname] = {"sname": sname, "vals": {}}

            pinfo = apinfo[mname][pname]

            if val not in pinfo["vals"]:
                if sname == "die":
                    pinfo["vals"][val] = {package: [die]}
                else:
                    pinfo["vals"][val] = [num]
            else:
                if sname == "die":
                    if package not in pinfo["vals"][val]:
                        pinfo["vals"][val][package] = []
                    pinfo["vals"][val][package].append(die)
                else:
                    pinfo["vals"][val].append(num)

            if sname != pinfo["sname"]:
                raise Error(f"BUG: varying scope name for property '{pname}': was "
                            f"'{pinfo['sname']}', now '{sname}'")

        return apinfo

    def _build_aggr_pinfo(self, pnames, optar, mnames, skip_ro, skip_unsupported):
        """
        Build and return the aggregate properties dictionary for properties in 'pnames'.

        The aggregate properties dictionary has the following format.

        {mname1: {pname1: {"sname": sname,
                           "vals": {val1: [list of CPUs/packages having value 'val1'],
                                    val2: [list of CPUs/packages having value 'val2'],
                                    ... and so on for all values ...},
                  ... and so on for all properties ...},
         ... and so on for all mechanisms ...},

        * mname1 - name of the first mechanism that was used for reading the properties.
        * pname1 - the first property name (e.g., 'pkg_cstate_limit').
        * sname - scope name that was used for reading the property, may be one of "CPU", "die",
                  "package". If it is "CPU", the per-CPU 'get_prop_cpus()' method was used, if
                  "die", the per-die 'get_prop_dies()' was used, if "package", the per-package
                  'get_prop_packages()' was used.
        * val, val2, etc - all the different values for the property.

        In other words, the aggregate dictionary essentially maps property values to the list of
        CPUs, dies, or packages having these values. It represents a "by value view". And there is
        additional information like mechanism name and scope name. The scope name ("sname") defines
        whether the values are for individual CPUs, dies, or packages.

        There is a complication related to the fact that die numbers are relative to package
        numbers. If "sname" is "package" or "CPU", the values are mapped to the list of integer
        package or CPU numbers. But if "sname" is "die", then they are mapped to a dictionary, not a
        list. The keys of the dictionary are integer package numbers, and the values of the
        dictionaries are lists of integer die numbers for the package (the key).

        So when 'sname' is die, then the aggregate properties dictionary has the following format:

          {mname1: {pname1: {"sname": sname,
                             "vals": {val1: {package0: [die numbers in package 0],
                                             package1: [die numbers in package 1]
                                             ... and so on for all dies ...},
                                      ... and so on for all values ...},
                    ... and so on for all properties ...},
           ... and so on for all mechanisms ...},
        """

        aggr_pinfo = {}

        for pname in pnames:
            prop = self._pobj.props[pname]
            if skip_ro and not prop["writable"]:
                continue

            try:
                apinfo = self._build_aggr_pinfo_pname(pname, optar, mnames, skip_unsupported)
            except CStates.ErrorUsePerCPU as err:
                # Inconsistent property value across package or die siblings. Use per-CPU access.
                _LOG.warning(err)
                apinfo = self._build_aggr_pinfo_pname(pname, optar, mnames, skip_unsupported,
                                                      override_sname="CPU")

            # Merge 'apinfo' to 'aggr_pinfo'.
            for mname, info in apinfo.items():
                if mname not in aggr_pinfo:
                    aggr_pinfo[mname] = {}
                aggr_pinfo[mname].update(info)

        return aggr_pinfo

    def _normalize_pnames(self, pnames, skip_ro=False):
        """Validate property names in 'pnames' and return a normalized list."""

        if pnames == "all":
            pnames = list(self._pobj.props)
        else:
            for pname in pnames:
                if pname not in self._pobj.props:
                    raise Error(f"unknown property name '{pname}'")

        if not skip_ro:
            return pnames
        return [pname for pname in pnames if self._pobj.props[pname]["writable"]]

    def print_props(self, pnames, optar, mnames=None, skip_ro=False, skip_unsupported=True,
                    group=False, action=None):
        """
        Read and print properties. The arguments are as follows.
          * pnames - names of the property to read and print.
          * optar - an '_OpTarget.OpTarget()' object representing the CPUs, cores, modules, etc to
                    print the properties for.
          * mnames - list of mechanism names allowed to be used for getting properties (default -
                     all mechanisms are allowed).
          * skip_unsupported - if 'True', unsupported properties are skipped. Otherwise
                               "not supported" is printed.
          * skip_ro - if 'False', read-only properties information will be printed, otherwise they
                      will be skipped.
          * group - whether to group properties by the mechanism (e.g., "sysfs", "msr", etc) when
                    printing.
          * action - an optional action word to include into the messages (nothing by default). For
                     example, if 'action' is "set to", the messages will be like "property <pname>
                     set to <value>". Applicable only to the "human" format.
        Returns the printed properties count.
        """

        pnames = self._normalize_pnames(pnames, skip_ro=skip_ro)
        aggr_pinfo = self._build_aggr_pinfo(pnames, optar, mnames, skip_ro, skip_unsupported)

        if self._fmt == "human":
            return self._print_aggr_pinfo_human(aggr_pinfo, group=group, action=action)
        return self._print_aggr_pinfo_yaml(aggr_pinfo)

    def __init__(self, pobj, cpuinfo, fobj=None, fmt="human"):
        """
        Initialize a class instance. The arguments are as follows.
          * pobj - a "properties" object ('PStates', 'CStates', etc) to print the properties for.
          * cpuinfo - a 'CPUInfo' object corresponding to the host the properties are read from.
          * fobj - a file object to print the output to (standard output by default).
          * fmt - the printing format.

        The following formats are supported.
          * human - a human-friendly, human-readable print format.
          * yaml - print in YAML format.
        """

        self._pobj = pobj
        self._cpuinfo = cpuinfo
        self._fobj = fobj
        self._fmt = fmt

        formats = {"human", "yaml"}
        if self._fmt not in formats:
            formats = ", ".join(formats)
            raise Error(f"unsupported format '{self._fmt}', supported formats are: {formats}")

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, unref_attrs=("_fobj", "_cpuinfo", "_pobj"))

class PStatesPrinter(_PropsPrinter):
    """This class provides API for printing P-states information."""

class PMQoSPrinter(_PropsPrinter):
    """This class provides API for printing PM QoS information."""

    def _format_value_human(self, pname, prop, val):
        """Format value 'val' of property described by 'prop' into the "human" format."""

        if pname == "latency_limit" and val == 0:
            # Per-CPU latency limit 0 means "no latency".
            return "0 (no limit)"
        if pname == "global_latency_limit" and val == 0:
            # The global latency limit 0 means "cannot tolerate any latency".
            return "0 (absolute minimum)"

        return super()._format_value_human(pname, prop, val)

class CStatesPrinter(_PropsPrinter):
    """This class provides API for printing C-states information."""

    def _adjust_aggr_pinfo_pcs_limit(self, aggr_pinfo, optar, mnames):
        """
        The aggregate properties information dictionary 'aggr_pinfo' includes the 'pkg_cstate_limit'
        property. This property is read/write in case the corresponding MSR is unlocked, and it is
        R/O if the MSR is locked. The goal of this method is to remove all the "locked" CPUs from
        the 'pkg_cstate_limit' key of 'aggr_pinfo'.
        """

        cpus = optar.get_cpus()
        for pinfo in aggr_pinfo.values():
            pcsl_info = pinfo.get("pkg_cstate_limit")
            if not pcsl_info:
                continue

            if set(pcsl_info) == {None}:
                # The 'pkg_cstate_limit' property is not supported, nothing to do.
                continue

            locked_cpus = set()
            for pvinfo in self._pobj.get_prop_cpus("pkg_cstate_limit_lock", cpus=cpus,
                                                   mnames=mnames):
                cpu = pvinfo["cpu"]
                if pvinfo["val"] == "on":
                    locked_cpus.add(cpu)

            if not locked_cpus:
                # There are no locked CPUs, nothing to do.
                continue

            if len(locked_cpus) == len(cpus):
                # All CPUs are locked, "pkg_cstate_limit" is considered read-only, and is removed.
                del pinfo["pkg_cstate_limit"]
                continue

            new_pcsl_info = {}
            for key, _cpus in pcsl_info.items():
                new_cpus = []
                for cpu in _cpus:
                    if cpu not in locked_cpus:
                        new_cpus.append(cpu)
                if new_cpus:
                    new_pcsl_info[key] = new_cpus

            pinfo["pkg_cstate_limit"] = new_pcsl_info

        return aggr_pinfo

    def _print_val_msg(self, val, name=None, cpus=None, prefix=None, suffix=None, action=None):
        """Format and print a message about 'name' and its value 'val'."""

        if cpus is None:
            sfx = ""
        else:
            cpus = self._fmt_cpus(cpus)
            sfx = f" for {cpus}"

        if suffix is not None:
            sfx = sfx + suffix

        if name is not None:
            pfx = f"{name}: "
        else:
            pfx = ""

        if action:
            pfx += f"{action} "

        msg = pfx
        if prefix is not None:
            msg = prefix + msg

        if val is None:
            val = "not supported"
        elif cpus is not None:
            val = f"'{val}'"

        msg += f"{val}{sfx}"
        self._print(msg)

    def _print_aggr_rcsinfo_human(self, aggr_rcsinfo, group=False, action=None):
        """
        Print the aggregate C-states information in "human" format. The arguments are as follows.
          * aggr_rcsinfo - the aggregate C-states information dictionary.
          * group - same as in 'print_props()'.
          * action - same as in 'print_props()'.
        """

        if not aggr_rcsinfo:
            self._print("This system does not support C-states")
            return 0

        if not group:
            prefix = None
            sub_prefix = " - "
        else:
            prefix = " - "
            sub_prefix = "    - "
            self._print(f"Source: {self._pobj.get_mechanism_descr('sysfs')}")

        printed = 0
        for csname, csinfo in aggr_rcsinfo.items():
            if "disable" not in csinfo:
                # Do not print the C-state if it's enabled/disabled status is unknown.
                continue

            printed += 1
            for val, cpus in csinfo["disable"].items():
                val = "off" if val else "on"
                self._print_val_msg(val, name=csname, cpus=cpus, action=action, prefix=prefix)

            for key, kinfo in csinfo.items():
                if key == "latency":
                    name = "expected latency"
                    suffix = " us"
                elif key == "residency":
                    name = "target residency"
                    suffix = " us"
                elif key == "desc":
                    name = "description"
                    suffix = None
                else:
                    continue

                for val, cpus in kinfo.items():
                    self._print_val_msg(val, name=name, prefix=sub_prefix, suffix=suffix)

        return printed

    def _print_aggr_rcsinfo_yaml(self, aggr_rcsinfo):
        """Print the aggregate C-states information in YAML format."""

        yaml_rcsinfo = {}

        for csname, csinfo in aggr_rcsinfo.items():
            for key, kinfo in csinfo.items():
                for val, cpus in kinfo.items():
                    if key == "disable":
                        key = "value"
                        val = "off" if val else "on"

                    if csname not in yaml_rcsinfo:
                        yaml_rcsinfo[csname] = []

                    yaml_rcsinfo[csname].append({key: val, "CPU": Trivial.rangify(cpus)})

        self._yaml_dump(yaml_rcsinfo)
        return len(yaml_rcsinfo)

    def print_props(self, pnames, optar, mnames=None, skip_ro=False,
                    skip_unsupported=True, group=False, action=None):
        """
        Read and print properties. The arguments are the same as in '_PropsPrinter.print_props()'.
        """

        pnames = self._normalize_pnames(pnames, skip_ro=skip_ro)
        aggr_pinfo = self._build_aggr_pinfo(pnames, optar, mnames, skip_ro, skip_unsupported)

        if skip_ro and "pkg_cstate_limit" in pnames:
            # Special case: the package C-state limit option is read-write in general, but if it is
            # locked, it is effectively read-only. Since 'skip_ro' is 'True', we need to adjust
            # 'aggr_pinfo'.
            aggr_pinfo = self._adjust_aggr_pinfo_pcs_limit(aggr_pinfo, optar, mnames)

        if self._fmt == "human":
            return self._print_aggr_pinfo_human(aggr_pinfo, group=group, action=action)
        return self._print_aggr_pinfo_yaml(aggr_pinfo)

    def _build_aggr_rcsinfo(self, csinfo_iter, keys):
        """
        Build the aggregate C-states information dictionary. The arguments are as follows.
          * csinfo_iter - an iterator yielding '(cpu, csinfo)' tuples.
          * keys - C-state keys which should be included in the aggregate C-states dictionary.
                   For example, "disable", "latency", "residency.

        This method is similar to '_build_aggr_pinfo()' and returns a dictionary of a similar
        structure.
        """

        aggr_rcsinfo = {}

        # C-states info 'csinfo' has the following format:
        #
        # {"POLL": {"disable": True, "latency": 0, "residency": 0, ...},
        #  "C1E": {"disable": False, "latency": 2, "residency": 1, ...},
        #  ...}
        for cpu, csinfo in csinfo_iter:
            for pname, values in csinfo.items():
                if pname not in aggr_rcsinfo:
                    aggr_rcsinfo[pname] = {}

                for name, val in values.items():
                    if name not in keys or val is None:
                        continue

                    if name not in aggr_rcsinfo[pname]:
                        aggr_rcsinfo[pname][name] = {val: [cpu]}
                    elif val not in aggr_rcsinfo[pname][name]:
                        aggr_rcsinfo[pname][name][val] = [cpu]
                    else:
                        aggr_rcsinfo[pname][name][val].append(cpu)

        return aggr_rcsinfo

    def print_cstates(self, csnames="all", cpus="all", skip_ro=False, group=False, action=None):
        """
        Read and print information about requestable C-states. The arguments are as follows.
          * csnames - C-state names to print information about (all C-states by default).
          * cpus - CPU numbers to read and print C-state information for (all CPUs by default).
          * skip_ro - skip printing read-only information, print only modifiable information.
          * group - whether to group properties by the mechanism (e.g., "sysfs", "msr", etc) when
                    printing.
          * action - an optional action word to include into the messages (nothing by default). For
                     example, if 'action' is "set to", the messages will be like "property <pname>
                     set to <value>". Applicable only to the "human" format.
        Returns the printed requestable C-states count.
        """

        if skip_ro:
            keys = {"disable"}
        else:
            keys = {"disable", "latency", "residency", "desc"}

        csinfo_iter = self._pobj.get_cstates_info(csnames=csnames, cpus=cpus)

        try:
            aggr_rcsinfo = self._build_aggr_rcsinfo(csinfo_iter, keys)
        except ErrorNotSupported as err:
            _LOG.warning(err)
            _LOG.info("C-states are not supported")
            return 0

        if self._fmt == "human":
            return self._print_aggr_rcsinfo_human(aggr_rcsinfo, group=group, action=action)

        return self._print_aggr_rcsinfo_yaml(aggr_rcsinfo)
