# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
Provide a capability of reading and changing EPP (Energy Performance Preference).
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import contextlib
from pepclibs import CPUModels
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs import Trivial, ClassHelpers
from pepclibs import _EPBase
from pepclibs.helperlibs.emul._EPBEmulFile import _EPB_POLICIES

if typing.TYPE_CHECKING:
    from typing import Final, Union
    from pepclibs import CPUInfo
    from pepclibs.msr import MSR, HWPRequest, HWPRequestPkg
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

# The minimum and maximum EPP values.
_EPP_MIN: Final[int] = 0
_EPP_MAX: Final[int] = 0xFF

class EPP(_EPBase.EPBase):
    """
    Provide a capability of reading and changing EPP (Energy Performance Preference).

    Public Methods:
        - get_vals(): read EPP value(s).
        - set_vals(): set EPP value(s).
        - get_cpu_val(): read EPP value for a specific CPU.
        - set_cpu_val(): set EPP value for a specific CPU.
        - close(): uninitialize the class instance.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 enable_cache: bool = True):
        """
        Initialize class instance.

        Args:
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            msr: An 'MSR.MSR' object, used only in some error cases to provide additional details in
                 error messages. Will be created on demand if not provided.
            enable_cache: Whether to enable caching.
        """

        super().__init__("EPP", pman=pman, cpuinfo=cpuinfo, msr=msr, enable_cache=enable_cache)

        self._hwpreq: HWPRequest.HWPRequest | None = None
        self._hwpreq_pkg: HWPRequestPkg.HWPRequestPkg | None = None

        sysfs_base = "/sys/devices/system/cpu/cpufreq/policy%d"
        self._sysfs_epp_path = sysfs_base + "/energy_performance_preference"
        self._sysfs_epp_policies_path = sysfs_base + "/energy_performance_available_preferences"

        # List of available EPP policies according to sysfs.
        self._epp_policies: list[str] = []

    def close(self):
        """Uninitialize the class instance."""

        ClassHelpers.close(self, close_attrs=("_hwpreq", "_hwpreq_pkg"))
        super().close()

    def _get_hwpreq(self) -> HWPRequest.HWPRequest:
        """
        Return an 'HWPRequest.HWPRequest' object.

        Returns:
            An instance of 'HWPRequest.HWPRequest'.
        """

        if not self._hwpreq:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPRequest

            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self) -> HWPRequestPkg.HWPRequestPkg:
        """
        Return an 'HWPRequestPkg.HWPRequestPkg' object.

        Returns:
            An instance of 'HWPRequestPkg.HWPRequestPkg'.
        """

        if not self._hwpreq_pkg:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import HWPRequestPkg

            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)
        return self._hwpreq_pkg

    def _get_available_policies(self, cpu: int) -> list[str]:
        """
        Return list of available EPP policies read from sysfs.

        Args:
            cpu: CPU number.

        Returns:
            List of available EPP policy names.
        """

        if not self._epp_policies:
            try:
                with self._pman.open(self._sysfs_epp_policies_path % cpu, "r") as fobj:
                    line: str = fobj.read()
                    line = line.strip()

                self._epp_policies = Trivial.split_csv_line(line, sep=" ")
            except Error:
                self._epp_policies = []

        return self._epp_policies

    def _validate_value(self, val: str | int, policy_ok: bool = False):
        """Refer to '_EPBase._validate_value()'."""

        if Trivial.is_int(val):
            Trivial.validate_value_in_range(int(val), _EPP_MIN, _EPP_MAX, what="EPP value")
        elif not policy_ok:
            raise ErrorNotSupported(f"EPP value must be an integer within [{_EPP_MIN},{_EPP_MAX}]")
        else:
            policies = self._get_available_policies(0)
            if not policies:
                raise ErrorNotSupported(f"No EPP policies supported{self._pman.hostmsg}, please "
                                        f"use instead an integer within [{_EPP_MIN},{_EPP_MAX}]")

            if val not in policies:
                policies_str = ", ".join(policies)
                raise ErrorNotSupported(f"EPP value must be one of the following EPP policies: "
                                        f"{policies_str}, or integer within "
                                        f"[{_EPP_MIN},{_EPP_MAX}]")

    def _read_from_msr(self, cpu: int) -> int:
        """Refer to '_EPBase._read_from_msr()'."""

        # Find out if EPP should be read from 'MSR_HWP_REQUEST' or 'MSR_HWP_REQUEST_PKG'.
        hwpreq_union: Union[HWPRequest.HWPRequest, HWPRequestPkg.HWPRequestPkg]
        hwpreq_union = hwpreq = self._get_hwpreq()

        if hwpreq.is_cpu_feature_pkg_controlled("epp", cpu):
            hwpreq_union = self._get_hwpreq_pkg()

        return hwpreq_union.read_cpu_feature_int("epp", cpu)

    def _write_to_msr(self, val: str | int, cpu: int):
        """Refer to '_EPBase._write_to_msr()'."""

        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control("epp", cpu)

        if not Trivial.is_int(val):
            raise Error(f"Cannot set EPP to '{val}' using MSR mechanism, because it is not an "
                        f"integer value")

        try:
            hwpreq.write_cpu_feature("epp", val, cpu)
        except Error as err:
            raise type(err)(f"Failed to set EPP{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _read_from_sysfs(self, cpu: int) -> str | int:
        """Refer to '_EPBase._read_from_sysfs()'."""

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get("epp", cpu, "sysfs")

        path = self._sysfs_epp_path % cpu
        try:
            with self._pman.open(path, "r") as fobj:
                val_str: str = fobj.read()
                val_str = val_str.strip()
        except ErrorNotFound as err:
            raise ErrorNotSupported(f"EPP sysfs entry not found for CPU {cpu}"
                                    f"{self._pman.hostmsg}:\n{err.indent(2)}") from err

        if Trivial.is_int(val_str):
            val = int(val_str)
            return self._pcache.add("epp", cpu, val, "sysfs")

        return self._pcache.add("epp", cpu, val_str, "sysfs")

    def _write_to_sysfs(self, val: str | int, cpu: int):
        """Refer to '_EPBase._write_to_sysfs()'."""

        self._pcache.remove("epp", cpu, "sysfs")
        val_str = str(val).strip()

        try:
            with self._pman.open(self._sysfs_epp_path % cpu, "r+") as fobj:
                try:
                    fobj.write(val_str)
                except Error as err:
                    proc_cpuinfo = self._cpuinfo.get_proc_cpuinfo()
                    if proc_cpuinfo["vendor"] == CPUModels.VENDOR_AMD and Trivial.is_int(val_str):
                        # AMD CPUs support only policy names. Raise a tailored error message.
                        errmsg = f"Numeric EPB values are not supported " \
                                 f"'{self._cpuinfo.cpudescr}'\nUse one of the following EPB " \
                                 f"policies: {', '.join(_EPB_POLICIES)}"
                        raise ErrorNotSupported(f"{errmsg}\n{err.indent(2)}") from err

                    if proc_cpuinfo["vendor"] != CPUModels.VENDOR_INTEL:
                        raise

                    # This is a workaround for a kernel bug, which has been fixed in v6.5:
                    #   03f44ffb3d5be cpufreq: intel_pstate: Fix energy_performance_preference for
                    #                 passive
                    # The bug is that write fails is the new value is the same as the current value.
                    fobj.seek(0)
                    val_str1: str = fobj.read()
                    val_str1 = val_str1.strip()
                    if val_str != val_str1:
                        raise
        except Error as err:
            if isinstance(err, ErrorNotFound):
                err = ErrorNotSupported(str(err))
            err1 = type(err)(f"Failed to set EPP for CPU {cpu} to {val_str}{self._pman.hostmsg}:\n"
                             f"{err.indent(2)}")
            setattr(err1, "cpu", cpu)
            raise err1 from err

        self._pcache.add("epp", cpu, val_str, "sysfs")
