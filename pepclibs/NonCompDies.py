# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Provide information about non-compute dies (dies without CPUs).

Non-compute dies are dies without CPUs. The Linux kernel topology subsystem does not expose them,
so they can be discovered via TPMI (Intel's Topology and Power Management Interface).
Non-compute dies correspond to UFS (Uncore Frequency Scaling) TPMI clusters without CPUs. In other
words, non-compute dies do not necessarily correspond to physical dies - they are logical entities
representing uncore frequency scaling units without CPUs.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
from pepclibs.helperlibs import Logging, ClassHelpers, LocalProcessManager
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

if typing.TYPE_CHECKING:
    from typing import TypedDict, Literal
    from pepclibs import TPMI
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    # TPMI "agent types" for a die. Non-compute dies never have "core" agent type. But it is
    # included here for completeness.
    AgentTypes = Literal["core", "cache", "io", "memory"]

    class NonCompDieInfoTypedDict(TypedDict, total=False):
        """
        A typed dictionary representing information about a non-compute die.

        Attributes:
            package: The package number the non-compute die belongs to.
            die: The non-compute die number.
            agent_types: A set of agent types present on the non-compute die.
            title: A short description of the non-compute die.
        """

        package: int
        die: int
        agent_types: set[AgentTypes]
        title: str

AGENT_TYPES: list[AgentTypes] = ["core", "cache", "io", "memory"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

class NonCompDies(ClassHelpers.SimpleCloseContext):
    """
    Provide information about non-compute dies.

    Public methods overview.
        - get_dies() - return non-compute dies indexed by package number.
        - get_dies_sets() - return non-compute dies as sets indexed by package number.
        - get_dies_info() - return detailed information about non-compute dies.
        - get_tpmi() - return or create an instance of the TPMI object.
    """

    def __init__(self, pman: ProcessManagerType | None = None, tpmi: TPMI.TPMI | None = None):
        """
        Initialize a class instance.

        Args:
            pman: The process manager object that defines the target host. If not provided, a local
                  process manager is created.
            tpmi: An instance of the TPMI class. If not provided, a new instance is created.
        """

        self._close_pman = pman is None
        self._close_tpmi = tpmi is None

        self._tpmi = tpmi
        self._tpmi_errmsg = ""

        if pman:
            self._pman = pman
        else:
            self._pman = LocalProcessManager.LocalProcessManager()

        self._discovered = False
        self._noncomp_dies: dict[int, list[int]] = {}
        self._noncomp_dies_sets: dict[int, set[int]] = {}
        self._noncomp_dies_info: dict[int, dict[int, NonCompDieInfoTypedDict]] = {}

    def close(self):
        """Uninitialize the class object."""

        _LOG.debug("Closing the '%s' class object", self.__class__.__name__)
        ClassHelpers.close(self, close_attrs=("_tpmi", "_pman"))

    def get_tpmi(self) -> TPMI.TPMI:
        """
        Return or create an instance of 'TPMI.TPMI' object.

        Returns:
            The 'TPMI.TPMI' object.

        Raises:
            ErrorNotSupported: if TPMI is not supported on the target system.
        """

        if self._tpmi:
            return self._tpmi

        if self._tpmi_errmsg:
            raise ErrorNotSupported(self._tpmi_errmsg)

        _LOG.debug("Creating an instance of 'TPMI.TPMI'")

        # pylint: disable-next=import-outside-toplevel
        from pepclibs import TPMI

        try:
            self._tpmi = TPMI.TPMI(pman=self._pman)
        except Exception as err:
            self._tpmi_errmsg = str(err)
            _LOG.debug(self._tpmi_errmsg)
            raise

        return self._tpmi

    def _discover_noncomp_dies(self):
        """Discover non-compute dies and build the internal data structures."""

        self._discovered = True

        try:
            tpmi = self.get_tpmi()
        except ErrorNotSupported:
            _LOG.debug("TPMI is not supported on the target system, cannot discover "
                       "non-compute dies")
            return

        _LOG.debug("Discovering non-compute dies via TPMI")

        for package, addr, instance, cluster in tpmi.iter_ufs_feature():
            regval = tpmi.read_ufs_register(addr, instance, cluster, "UFS_STATUS")

            if tpmi.get_bitfield(regval, "ufs", "UFS_STATUS", "AGENT_TYPE_CORE"):
                _LOG.debug("Skipping a compute die at package %d, addr %s, instance %d, cluster %d",
                           package, addr, instance, cluster)
                continue

            die = instance + cluster
            self._noncomp_dies.setdefault(package, []).append(die)
            self._noncomp_dies_sets.setdefault(package, set()).add(die)

            agent_types = set()
            for agent_type in AGENT_TYPES:
                if tpmi.get_bitfield(regval, "ufs", "UFS_STATUS",
                                     f"AGENT_TYPE_{agent_type.upper()}"):
                    agent_types.add(agent_type)

            # Format the description so that it would have a form of:
            # - x: if there is only one agent.
            # - x and y: if there are two agents.
            # - x, y, and z: if there are three or more agents.
            # Also, use "I/O" instead of "io".
            agents = []
            for agent_type in AGENT_TYPES:
                if agent_type not in agent_types:
                    continue
                if agent_type == "io":
                    agents.append("I/O")
                else:
                    agents.append(agent_type)

            if len(agents) == 1:
                title = f"{agents[0]}"
            elif len(agents) == 2:
                title = f"{agents[0]} and {agents[1]}"
            else:
                title = ", ".join(agents[:-1]) + f", and {agents[-1]}"

            pkg_info = self._noncomp_dies_info.setdefault(package, {})
            die_info = pkg_info.setdefault(die, {})
            die_info["package"] = package
            die_info["die"] = die
            die_info["agent_types"] = agent_types
            die_info["title"] = title[0].upper() + title[1:]

    def get_dies(self) -> dict[int, list[int]]:
        """
        Return a dictionary mapping package numbers to lists of non-compute die numbers.

        Returns:
            The non-compute dies dictionary: {package: [die1, die2, ...]}. Packages and dies are in
            the ascending order.
        """

        if not self._discovered:
            self._discover_noncomp_dies()

        return self._noncomp_dies

    def get_dies_sets(self) -> dict[int, set[int]]:
        """
        Return a dictionary mapping package numbers to sets of non-compute die numbers.

        Returns:
            The non-compute dies sets dictionary: {package: {die1, die2, ...}}. Packages and dies
            are in the ascending order.
        """

        if not self._discovered:
            self._discover_noncomp_dies()

        return self._noncomp_dies_sets

    def get_dies_info(self) -> dict[int, dict[int, NonCompDieInfoTypedDict]]:
        """
        Return detailed information about non-compute dies.

        Returns:
            The non-compute dies information dictionary:
            {package: {die: NonCompDieInfoTypedDict, ...}}. Packages and dies are in the ascending
            order.
        """

        if not self._discovered:
            self._discover_noncomp_dies()

        return self._noncomp_dies_info
