# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
#  Authors: Antti Laakso <antti.laakso@intel.com>
#           Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module implements the 'PepcPCStates' class, which handles 'pepc' P-state and C-state commands.
"""

from pepctool import _PepcCommon
from pepclibs.helperlibs import ClassHelpers

class PepcPCStates(ClassHelpers.SimpleCloseContext):
    """
    This class provides interface to set and print C-state and P-state properties.

    Public methods overview.
      * set multiple C-state or P-state properties for multiple CPUs: 'set_props()'.
      * print multiple C-state or P-state properties for multiple CPUs: 'print_props()'.
    """

    def set_props(self, props, cpus):
        """
        Set multiple properties 'props' for multiple CPUs 'cpus'. The arguments are as follows.
          * props - A dictionary with property names as keys and property values as values.
          * cpus - list of CPU numbers to set the properties for.
        """

        self._pcobj.set_props(props, cpus)
        for pname in props:
            # Read back the just set value in order to get "resolved" values. For example, "min"
            # would be resolved to the actual frequency number.
            _, pinfo = next(self._pcobj.get_props((pname,), cpus=cpus))
            val = pinfo[pname][pname]
            _PepcCommon.print_prop_msg(self._pcobj.props[pname], val, self._cpuinfo,
                                       action="set to", cpus=cpus)

    def print_props(self, pnames, cpus, skip_unsupported):
        """
        Read and print values of multiple properties for multiple CPUs. The argument are as follows.
          * pnames - property names as a list of strings. For property names, see 'PROPS' in
                     'PStates' and 'CStates' modules.
          * cpus - list of CPU numbers to print the property values for.
          * skip_unsupported - if 'True', do not print unsupported values.
        """

        pinfo_iter = self._pcobj.get_props(pnames, cpus=cpus)
        aggr_pinfo = _PepcCommon.build_aggregate_pinfo(pinfo_iter)

        _PepcCommon.print_aggr_props(aggr_pinfo, self._pcobj, self._cpuinfo, skip_unsupported)

    def __init__(self, pcobj, cpuinfo):
        """
        The class constructor. The arguments are as follows.
          * pcobj - the 'CStates' or 'PStates' object.
          * cpuinfo - the 'CPUInfo' object.
        """

        self._pcobj = pcobj
        self._cpuinfo = cpuinfo

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, unref_attrs=("_pcobj", "_cpuinfo"))
