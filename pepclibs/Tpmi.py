# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""
Provide capability for reading and writing TPMI registers on Intel CPUs. TPMI stands for "Topology
Aware Register and PM Capsule Interface" and is a  memory mapped interface for accessing power
management features on Intel CPUs, in addition to the existing MSRs.

Terminology.
  * feature - a group of TPMI registers exposed by the processor via PCIe VSEC (Vendor-Specific
              Extended Capabilities) as a single capability. Typically TPMI feature corresponds to
              a real processor feature. For example, "uncore" TPMI feature includes processor
              registers related to uncore frequency scaling. The "rapl" TPMI feature includes
              processor registers related to processor's Running Average Power Limit (RAPL) feature.
              The "sst" feature includes processor registers related to Intel Speed Select
              Technology (SST) feature.
  * feature ID - a unique integer number assigned to a feature.
  * spec file - a YAML file describing the registers and bitfields for a TPMI feature. Each
                supported feature has a spec file, and each spec file corresponds to a feature. A
                spec file is also required to decode the TPMI feature's PCIe VSEC table.
  * feature dictionary - a dictionary describing a TPMI feature registers, bit fields and other
                         details. Feature dictionary is formed based on the feature spec file
                         contents.
"""

import logging
import os
import re
from pathlib import Path
from pepclibs.helperlibs import ProjectFiles, YAML
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

_SPECS_PATH_ENVVAR = "PEPC_TPMI_DATA_PATH"
_LOG = logging.getLogger()

class Tpmi():
    """
    Provide API for reading and writing TPMI registers on Intel CPUs.
    """

    def _get_fdict(self, fname):
        """
        Return the feature dictionary feature 'fname'. If the dictionary is not available in the
        cache, loaded it from the spec file.
        """

        if fname in self._fdict_cache:
            return self._fdict_cache[fname]

        for spec_dir in self._spec_dirs:
            specpath = spec_dir / (fname + ".yaml")
            if specpath.exists():
                spec = YAML.load(specpath)

            self._fdict_cache[fname] = spec

        if fname not in self._fdict_cache:
            raise ErrorNotSupported("TPMI feature '{fname}' is not supported")

        return self._fdict_cache[fname]

    def _get_supported_fnames_and_fids(self):
        """
        Yield '(fname, fid)' tuples for every feature supported via the available spec files. Note,
        this method ends up loading the spec file for every supported feature so it may be
        expensive.
        """

        if not self._fdict_cache:
            for spec_dir in self._spec_dirs:
                for specname in os.listdir(spec_dir):
                    match = re.match(r"^(.*).yaml", specname)
                    if match:
                        fname = match.group(1)
                        fdict = YAML.load(spec_dir / specname)
                        self._fdict_cache[fname] = fdict

        for fname, fdict in self._fdict_cache.items():
            fid = fdict["feature-id"]
            yield fname, fid

    def __init__(self):
        """The class constructor."""

        self._fdict_cache = {}
        self._spec_dirs = []

        path = os.getenv(_SPECS_PATH_ENVVAR)
        if path:
            path = Path(path)
            if not path.exists():
                _LOG.warning("TPMI spec files path '%s' specified in the '%s' environment "
                             "variable does not exist, ignoring it", path, _SPECS_PATH_ENVVAR)
            else:
                self._spec_dirs.append(path)

        self._spec_dirs.append(ProjectFiles.find_project_data("pepc", "tpmi",
                                                              what="TPMI spec files"))
