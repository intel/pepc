# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Antti Laakso <antti.laakso@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>

"""
This module implements CPU properties caching.
"""

from pepclibs import CPUInfo
from pepclibs.helperlibs import ClassHelpers
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound

class PropsCache():
    """
    This class implements properties caching. The cache is indexed by property name and CPU number.
    It takes the CPU scope (global 0, package 3, etc) into account as well. The cache uses the
    write-through policy.
    """

    def is_cached(self, pname, cpu, mname):
        """
        Check if '(pname, cpu, mname)' exists in the cache. Return 'True' if the item was found and
        'False' otherwise. Arguments are the same as in 'get()'.
        """

        try:
            self.get(pname, cpu, mname)
        except Error:
            return False
        return True

    def find(self, pname, cpu, mnames=None):
        """
        Similar to 'get()', but 'mnames' argument specifies the list of mechanism names. Search for
        the '(pname, cpu)' item with mechanism name from 'mnames', and return the first matched
        item, along with the mechanism name. The argument are as follows.
          * pname - name of the property to find.
          * cpu - an integer CPU number.
          * mnames - a collection of mechanism names to use for searching. By default, search for
                     items with any mechanism name.

        Return a '(val, mname)' tuple in the item was found, raise 'ErrorNotFound' otherwise.
        """

        if not self._enable_cache:
            raise ErrorNotFound("caching is disabled")

        if mnames is None:
            mnames = self._cache

        for mname in mnames:
            try:
                return (self._cache[mname][pname][cpu], mname)
            except KeyError:
                pass

        mnames = ",".join(mnames)
        raise ErrorNotFound(f"property '{pname}' and mechanisms '{mnames}' are not cached for "
                            f"CPU {cpu}")

    def get(self, pname, cpu, mname):
        """
        Look up the '(pname, cpu, mname)' in the cache. The argument are as follows.
          * pname - name of the property.
          * cpu - an integer CPU number.
          * mname - mechanism name for the property.

        Return the value if the item was found, raise 'ErrorNotFound' otherwise.
        """

        if not self._enable_cache:
            raise ErrorNotFound("caching is disabled")

        try:
            return self._cache[mname][pname][cpu]
        except KeyError:
            raise ErrorNotFound(f"property '{pname}' and mechanism '{mname}' are not cached for "
                                f"CPU {cpu}") from None

    def remove(self, pname, cpu, mname, sname="CPU"):
        """
        Remove '(pname, cpu)' and all the other items sharing the same scope from the cache.
          * pname - name of the property.
          * cpu - an integer CPU number.
          * mname - mechanism name for the property (see a note in 'get()' docstring).
          * sname - name of scope (e.g. "package", "core").
        """

        if not self._enable_cache:
            return

        if sname == "global":
            del self._cache[mname][pname]
            return

        cpus = self._cpuinfo.get_cpu_siblings(cpu, sname)

        for cpu in cpus: # pylint: disable=redefined-argument-from-local
            try:
                del self._cache[mname][pname][cpu]
            except KeyError:
                pass

    def add(self, pname, cpu, val, mname, sname="CPU"):
        """
        Add value 'val' for item '(pname, cpu)' to the cache. Add it also for each CPU sharing the
        same scope. The argument are as follows.
          * pname - name of the property.
          * cpu - an integer CPU number.
          * val - value to get cached.
          * mname - mechanism name for the property (see a note in 'get()' docstring).
          * sname - name of scope (e.g. "package", "core").

        Return 'val'.
        """

        if not self._enable_cache:
            return val

        cpus = self._cpuinfo.get_cpu_siblings(cpu, sname)

        if mname not in self._cache:
            self._cache[mname] = {}
        if pname not in self._cache[mname]:
            self._cache[mname][pname] = {}
        for cpu in cpus: # pylint: disable=redefined-argument-from-local
            self._cache[mname][pname][cpu] = val

        return val

    def __init__(self, cpuinfo=None, pman=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * enable_cache - this argument can be used to disable caching.
        """

        self._enable_cache = enable_cache
        self._cpuinfo = cpuinfo

        self._close_cpuinfo = cpuinfo is None

        if not self._enable_cache:
            return

        if not self._cpuinfo:
            # 'pman' is only used to initialize 'cpuinfo' in this class.
            self._cpuinfo = CPUInfo.CPUInfo(pman=pman)

        self._cache = {}

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_cpuinfo",))
