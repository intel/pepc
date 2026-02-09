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
from pepclibs import CPUInfo, _PropsCache
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import Final, NoReturn, Callable, Generator, Sequence, Iterable, Literal
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
            enable_cache: Whether to enable caching.
        """

        self._what = what
        self._pman: ProcessManagerType
        self._cpuinfo: CPUInfo.CPUInfo
        self._msr: MSR.MSR | None = msr
        self._enable_cache = enable_cache

        # EPP/EPB scope name.
        self.sname: ScopeNameType = "CPU"

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        if not pman:
            self._pman = LocalProcessManager.LocalProcessManager()
        else:
            self._pman = pman

        if not cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)
        else:
            self._cpuinfo = cpuinfo

        # The per-CPU cache for read-only data, such as policies list. MSR implements its own
        # caching.
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=enable_cache)

    def close(self):
        """Uninitialize the class instance."""

        close_attrs = ("_msr", "_cpuinfo", "_pman", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)

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
        Validate EPP value.

        Args:
            val: EPP value to validate.
            policy_ok: If True, allow policy names in addition to numeric values.
        """

        raise NotImplementedError("BUG: '_validate_value()' method is not implemented in the child "
                                  "class")

    def _read_from_msr(self, cpu: int) -> int:
        """
        Read EPP for CPU 'cpu' from MSR.

        Args:
            cpu: CPU number.

        Returns:
            EPP value for the CPU.

        Raises:
            ErrorNotSupported: If EPP MSR is not supported or disabled.
        """

        raise NotImplementedError("BUG: '_read_from_msr()' method is not implemented in the child "
                                  "class")

    def _write_to_msr(self, val: str | int, cpu: int):
        """
        Write EPP 'epp' for CPU 'cpu' to MSR.

        Args:
            val: EPP value to write.
            cpu: CPU number.
        """

        raise NotImplementedError("BUG: '_write_to_msr()' method is not implemented in the child "
                                  "class")

    def _read_from_sysfs(self, cpu: int) -> str | int:
        """
        Read EPP for CPU 'cpu' from sysfs.

        Args:
            cpu: CPU number.

        Returns:
            EPP value for the CPU.

        Raises:
            ErrorNotSupported: If EPP sysfs entry is not found.
        """

        raise NotImplementedError("BUG: '_read_from_sysfs()' method is not implemented in the "
                                  "child class")

    def _write_to_sysfs(self, val: str | int, cpu: int):
        """
        Write EPP 'epp' for CPU 'cpu' to sysfs.

        Args:
            val: EPP value to write.
            cpu: CPU number.

        Returns:
            The cached EPP value after writing.
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

        for mname in mnames:
            func: Callable[[int], str | int]
            if mname == "sysfs":
                func = self._read_from_sysfs
            else:
                func = self._read_from_msr

            try:
                for cpu in cpus:
                    val = func(cpu)
                    yield (cpu, val, mname)
                    yielded += 1
            except ErrorNotSupported as err:
                if not yielded:
                    errors.append(err)
                    continue
                raise

            return

        self._raise_getset_exception(cpus, mnames, "get", errors)

    def _set_epb_or_epb(self,
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
        set_cpus = 0

        for mname in mnames:
            if mname == "sysfs":
                func = self._write_to_sysfs
                policy_ok = True
            else:
                func = self._write_to_msr
                policy_ok = False

            cpu = 0
            try:
                self._validate_value(val, policy_ok=policy_ok)
                for cpu in cpus:
                    func(str(val), cpu)
                    set_cpus += 1
            except ErrorNotSupported as err:
                if not set_cpus:
                    errors.append(err)
                    continue
                raise

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

        return self._set_epb_or_epb(val, cpus=cpus, mnames=mnames)

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

        return self._set_epb_or_epb(val, cpus=(cpu,), mnames=mnames)
