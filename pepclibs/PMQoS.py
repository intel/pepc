# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide a capability of retrieving and setting Linux PM QoS properties.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs import _PropsClassBase
from pepclibs.PMQoSVars import PROPS
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import Generator, Sequence
    from pepclibs import _SysfsIO, CPUInfo, _LinuxPMQoS
    from pepclibs.msr import MSR
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType
    from pepclibs.PropsTypes import PropertyValueType, MechanismNameType
    from pepclibs.CPUInfoTypes import AbsNumsType

class PMQoS(_PropsClassBase.PropsClassBase):
    """
    Provide API for managing platform settings related to PM QoSs. Refer to
    '_PropsClassBase.PropsClassBase' docstring for public methods overview.
    """

    def __init__(self,
                 pman: ProcessManagerType | None = None,
                 cpuinfo: CPUInfo.CPUInfo | None = None,
                 msr: MSR.MSR | None = None,
                 sysfs_io: _SysfsIO.SysfsIO | None = None,
                 enable_cache: bool = True):
        """Refer to 'PropsClassBase.__init__()'."""

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr, sysfs_io=sysfs_io,
                         enable_cache=enable_cache)

        self._linux_pmqos_obj: _LinuxPMQoS.LinuxPMQoS | None = None

        self._init_props_dict(PROPS)

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_linux_pmqos_obj",)
        ClassHelpers.close(self, close_attrs=close_attrs)

        super().close()

    def _get_linux_pmqos_obj(self) -> _LinuxPMQoS.LinuxPMQoS:
        """
        Return an instance of 'LinuxPMQoS'.

        Returns:
           The cached or newly created 'LinuxPMQos' object.
        """

        if not self._linux_pmqos_obj:
            from pepclibs import _LinuxPMQoS # pylint: disable=import-outside-toplevel

            sysfs_io = self._get_sysfs_io()
            self._linux_pmqos_obj = _LinuxPMQoS.LinuxPMQoS(pman=self._pman, sysfs_io=sysfs_io,
                                                           enable_cache=self._enable_cache)
        return self._linux_pmqos_obj

    def _get_prop_cpus(self,
                       pname: str,
                       cpus: AbsNumsType,
                       mname: MechanismNameType,
                       mnames: Sequence[MechanismNameType]) -> \
                                            Generator[tuple[int, PropertyValueType], None, None]:
        """Refer to 'PropsClassBase._get_prop_cpus()'."""

        linux_pmqos_obj = self._get_linux_pmqos_obj()

        if pname == "latency_limit":
            yield from linux_pmqos_obj.get_latency_limit(cpus)
        elif pname == "global_latency_limit":
            limit = linux_pmqos_obj.get_global_latency_limit()
            for cpu in cpus:
                yield (cpu, limit)
        else:
            raise Error(f"BUG: Unknown property '{pname}'")

    def _set_prop_cpus(self,
                       pname: str,
                       val: PropertyValueType,
                       cpus: AbsNumsType,
                       mname: MechanismNameType,
                       mnames: Sequence[MechanismNameType]):
        """Refer to 'PropsClassBase._set_prop_cpus()'."""

        linux_pmqos_obj = self._get_linux_pmqos_obj()

        if pname == "latency_limit":
            linux_pmqos_obj.set_latency_limit(val, cpus)
        else:
            raise Error(f"BUG: Unknown property '{pname}'")
