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
Provide the base class for 'EPP' and 'EPB' modules.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers, Trivial
from pepclibs import CPUInfo
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Final, NoReturn, Callable, Generator, Sequence, Iterable, Literal
    from pepclibs import _SysfsIO
    from pepclibs.msr import MSR
    from pepclibs.CPUInfoTypes import ScopeNameType
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.helperlibs.Exceptions import ExceptionTypeType

# Supported mechanism names.
_MNAMES: Final[tuple[str, ...]] = ("sysfs", "msr")

class EPBase(ClassHelpers.SimpleCloseContext):
    """
    Provide the base class for 'EPP' and 'EPB' modules.
    """

    def __init__(self,
                 what: str,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """
        Initialize class instance.

        Args:
            what: Should be "EPP" or "EPB".
            pman: Process manager for the target host. The local host will be used if not provided.
            cpuinfo: The CPU information object for the target system. Will be created if not
                     provided.
            msr: An 'MSR.MSR' object which should be used for accessing MSR registers. Will be
                 created on demand if not provided.
            sysfs_io: A '_SysfsIO.SysfsIO' object for sysfs access. Will be created on demand if not
                      provided.
            enable_cache: Whether to enable caching.
        """

        self._what = what
        self._pman: ProcessManagerType
        self._cpuinfo: CPUInfo.CPUInfo
        self._msr: MSR.MSR | None = msr
        self._sysfs_io: _SysfsIO.SysfsIO | None = sysfs_io
        self._enable_cache = enable_cache

        # EPP/EPB scope name.
        self.sname: ScopeNameType = "CPU"

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None
        self._close_sysfs_io = sysfs_io is None

        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        if not cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        else:
            self._cpuinfo = cpuinfo

        # Whether the platform supports EPP/EPB for each CPU.
        self._supported: dict[int, bool] = self._build_supported_dict()

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_msr", "_cpuinfo", "_pman", "_sysfs_io")
        ClassHelpers.close(self, close_attrs=close_attrs)

    def _build_supported_dict(self) -> dict[int, bool]:
        """"
        Build the per-CPU dictionary with boolean values indicating whether EPP/EPB is supported for
        each CPU.

        Returns:
            Dictionary with CPU numbers as keys and boolean values indicating whether EPP/EPB is
            supported for each CPU.
        """

        if self._what == "EPB":
            return {cpu: True for cpu in self._cpuinfo.get_cpus()}
        if self._what == "EPP":
            pcinfo = self._cpuinfo.get_proc_percpuinfo()
            return {cpu: "hwp_epp" in pcinfo["flags"][cpu] for cpu in self._cpuinfo.get_cpus()}

        raise Error(f"BUG: unknown self._what='{self._what}'")

    def _get_msr(self) -> MSR.MSR:
        """
        Return an 'MSR.MSR' object.

        Returns:
            An instance of 'MSR.MSR'.
        """

        if not self._msr:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.msr import MSR

            self._msr = MSR.MSR(self._cpuinfo, pman=self._pman, enable_cache=self._enable_cache)
        return self._msr

    def _get_sysfs_io(self) -> _SysfsIO.SysfsIO:
        """
        Return an instance of '_SysfsIO.SysfsIO'.

        Returns:
            An instance of '_SysfsIO.SysfsIO'.
        """

        if not self._sysfs_io:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs import _SysfsIO

            self._sysfs_io = _SysfsIO.SysfsIO(self._pman, enable_cache=self._enable_cache)

        return self._sysfs_io

    @staticmethod
    def _normalize_mnames(mnames: Sequence[str]) -> list[str]:
        """
        Validate and normalize mechanism names in 'mnames'.

        Args:
            mnames: List of mechanism names to validate. Empty sequence means "all supported
                    mechanisms".

        Returns:
            List of validated and deduplicated mechanism names.
        """

        if not mnames:
            return list(_MNAMES)

        for mname in mnames:
            if mname in _MNAMES:
                continue
            mnames_str = ", ".join(_MNAMES)
            raise Error(f"BUG: bad mechanism name '{mname}', supported mechanisms are: "
                        f"{mnames_str}")

        return Trivial.list_dedup(mnames)

    def _raise_getset_exception(self,
                                cpus: list[int],
                                mnames: list[str],
                                action: str,
                                errors: list[Error]) -> NoReturn:
        """
        Raise an exception for get or set method when EPP/EPB could not be read or set.

        Args:
            cpus: List of CPU numbers that failed.
            mnames: List of mechanism names that were tried.
            action: Action string ('get' or 'set').
            errors: List of error exceptions encountered.

        Raises:
            ErrorNotSupported: Always raised with detailed error message.
        """

        if len(mnames) > 1:
            mnames_str = f"using {','.join(mnames)} methods"
        else:
            mnames_str = f"using the {mnames[0]} method"

        cpus_range = Trivial.rangify(cpus)
        errmsg = f"Failed to {action} {self._what} {mnames_str} for the following CPUs {cpus_range}"

        if errors:
            errmsg += "\n" + "\n".join([err.indent(2) for err in errors])
            raise ErrorNotSupported(errmsg) from errors[0]
        raise ErrorNotSupported(errmsg)

    def _validate_value(self, val: str | int, policy_ok: bool = False):
        """
        Validate EPP/EPB value.

        Args:
            val: EPP/EPB value to validate.
            policy_ok: If True, allow policy names in addition to numeric values.
        """

        raise NotImplementedError("BUG: '_validate_value()' method is not implemented in the child "
                                  "class")

    def _fetch_from_msr(self, cpus: Sequence[int]) -> Generator[tuple[int, int], None, None]:
        """
        Fetch EPB or EPP for CPUs in 'cpus' from MSR.

        Args:
            cpus: Collection of integer CPU numbers (already normalized).

        Yields:
            Tuple of (cpu, value) for each CPU.

        Raises:
            ErrorNotSupported: If EPP/EPB MSR is not supported or disabled.
        """

        raise NotImplementedError("BUG: '_fetch_from_msr()' method is not implemented in the child "
                                  "class")
    def _write_to_msr(self, val: str | int, cpus: Sequence[int]):
        """
        Write EPB or EPP for CPUs in 'cpus' to MSR.

        Args:
            val: The EPB/EPP value to write.
            cpus: Collection of integer CPU numbers (already normalized).
        """

        raise NotImplementedError("BUG: '_write_to_msr()' method is not implemented in the child "
                                  "class")

    def _fetch_from_sysfs(self,
                          cpus: Sequence[int]) -> Generator[tuple[int, str | int], None, None]:
        """
        Fetch EPB or EPP for CPUs in 'cpus' from sysfs.

        Args:
            cpus: Collection of integer CPU numbers (already normalized).

        Yields:
            Tuple of (cpu, value) for each CPU.

        Raises:
            ErrorNotSupported: If EPP/EPB sysfs entry is not found for any of the CPUs.
        """

        raise NotImplementedError("BUG: '_fetch_from_sysfs()' method is not implemented in the "
                                  "child class")

    def _write_to_sysfs(self, val: str | int, cpus: Sequence[int]):
        """
        Write EPB or EPP for CPUs in 'cpus' to sysfs.

        Args:
            val: The EPB/EPP value to write.
            cpus: Collection of integer CPU numbers (already normalized).
        """

        raise NotImplementedError("BUG: '_write_to_sysfs()' method is not implemented in the child "
                                  "class")

    def _get_epp_or_epb(self,
                        cpus: Iterable[int] | Literal["all"],
                        mnames: Sequence[str]) -> Generator[tuple[int, str | int, str], None, None]:
        """
        Yield EPB or EPP for CPUs in 'cpus'.

        Args:
            cpus: Collection of integer CPU numbers.
            mnames: List of mechanisms to use for reading.

        Yields:
            Tuple of (cpu, value, mname) for each CPU.
        """

        mnames = self._normalize_mnames(mnames)
        cpus = self._cpuinfo.normalize_cpus(cpus)
        errors: list[Error] = []
        yielded = 0

        for cpu in cpus:
            if not self._supported.get(cpu, False):
                raise ErrorNotSupported(f"{self._what} is not supported for CPU {cpu}"
                                        f"{self._pman.hostmsg}")

        for mname in mnames:
            func: Callable[[Sequence[int]], Generator[tuple[int, str | int], None, None]]
            if mname == "sysfs":
                func = self._fetch_from_sysfs
            else:
                func = self._fetch_from_msr

            try:
                for cpu, val in func(cpus):
                    yield (cpu, val, mname)
                    yielded += 1
            except ErrorNotSupported as err:
                if not yielded:
                    errors.append(err)
                    continue
                raise

            return

        self._raise_getset_exception(cpus, mnames, "get", errors)

    def _set_epp_or_epb(self,
                        val: str | int,
                        cpus: Iterable[int] | Literal["all"],
                        mnames: Sequence[str]) -> str:
        """
        Set EPB or EPP for CPUs in 'cpus' using the 'mname' mechanism.

        Args:
            val: The EPB or EPP value to set. Can be an integer, a string representing an integer.
                 If 'mname' is "sysfs", 'val' can also be EPB or EPP policy name (e.g.,
                 "performance").
            cpus: Collection of integer CPU numbers. Special value 'all' means "all CPUs".
            mnames: List of mechanisms to use for setting EPB or EPP. The mechanisms will be tried
                    in the order specified in 'mnames'. Specify an empty sequence to try all
                    supported mechanisms.

        Returns:
            Name of the mechanism that was used for setting.

        Raises:
            ErrorNotSupported: If the platform does not support EPB/EPP.
        """

        mnames = self._normalize_mnames(mnames)
        cpus = self._cpuinfo.normalize_cpus(cpus)
        errors: list[Error] = []

        for cpu in cpus:
            if not self._supported.get(cpu, False):
                raise ErrorNotSupported(f"{self._what} is not supported for CPU {cpu}"
                                        f"{self._pman.hostmsg}")

        for mname in mnames:
            func: Callable[[str | int, Sequence[int]], None]
            if mname == "sysfs":
                func = self._write_to_sysfs
                policy_ok = True
            else:
                func = self._write_to_msr
                policy_ok = False

            try:
                self._validate_value(val, policy_ok=policy_ok)
                func(val, cpus)
            except ErrorNotSupported as err:
                errors.append(err)
                continue

            return mname

        # None of the methods worked.
        self._raise_getset_exception(cpus, mnames, "set", errors)

    def get_vals(self,
                 cpus: Iterable[int] | Literal["all"] = "all",
                 mnames: Sequence[str] = ()) -> Generator[tuple[int, str | int, str], None, None]:
        """
        Read EPP or EPB for CPUs 'cpus' using mechanisms in 'mnames'.

        Args:
            cpus: Collection of integer CPU numbers to read EPP or EPB for. Special value 'all'
                  means "all CPUs" (default).
            mnames: List of mechanisms to use for reading EPP/EPB. The mechanisms will be tried in
                    the order specified in 'mnames'. Try all supported mechanisms by default.
        Yields:
            Tuple of (cpu, value, mname) for every CPU in 'cpus'.
        """

        yield from self._get_epp_or_epb(cpus, mnames)

    def get_cpu_val(self, cpu: int, mnames: Sequence[str] = ()) -> tuple[str | int, str]:
        """
        Read EPP or EPB for CPU 'cpu' using mechanisms in 'mnames'.

        Args:
            cpu: CPU number to read EPP or EPB for.
            mnames: List of mechanisms to use for reading EPP/EPB. The mechanisms will be tried in
                    the order specified in 'mnames'. Try all supported mechanisms by default.

        Returns:
            Tuple of (value, mname).
        """

        _, val, mname = next(self._get_epp_or_epb((cpu,), mnames))
        return val, mname

    def set_vals(self,
                 val: str | int,
                 cpus: Iterable[int] | Literal["all"] = "all",
                 mnames: Sequence[str] = ()) -> str:
        """
        Set EPP or EPB for CPUs in 'cpus' using the 'mname' mechanism.

        Args:
            val: The EPP/EPB value to set. Can be an integer or a string representing an integer.
                 If 'mname' is "sysfs", 'val' can also be EPP/EPB policy name (e.g.,
                 "performance").
            cpus: Collection of integer CPU numbers to set EPP or EPB for. Special value 'all' means
                  "all CPUs" (default).
            mnames: List of mechanisms to use for setting EPP/EPB. The mechanisms will be tried in
                    the order specified in 'mnames'. Try all supported mechanisms by default.

        Returns:
            Name of the mechanism that was used for setting EPP or EPB.

        Raises:
            ErrorNotSupported: If the platform does not support EPP/EPB.
        """

        return self._set_epp_or_epb(val, cpus=cpus, mnames=mnames)

    def set_cpu_val(self,
                    val: str | int,
                    cpu: int,
                    mnames: Sequence[str] = ()) -> str:
        """
        Set EPP or EPB for CPU 'cpu' using the 'mname' mechanism.

        Args:
            val: The EPP/EPB value to set. Can be an integer or a string representing an integer.
                 If 'mname' is "sysfs", 'val' can also be EPP/EPB policy name (e.g.,
                 "performance").
            cpu: CPU number to set EPP or EPB for.
            mnames: List of mechanisms to use for setting EPP/EPB. The mechanisms will be tried in
                    the order specified in 'mnames'. Try all supported mechanisms by default.

        Returns:
            Name of the mechanism that was used for setting EPP or EPB.

        Raises:
            ErrorNotSupported: If the platform does not support EPP/EPB.
        """

        return self._set_epp_or_epb(val, cpus=(cpu,), mnames=mnames)
