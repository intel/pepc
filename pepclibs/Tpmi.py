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

  * spec files directory - a directory containing spec files (one or many). There may be multiple
                           spec files directories.

  * feature dictionary - a dictionary describing a TPMI feature registers, bit fields and other
                         details. Feature dictionary is formed based on the feature spec file
                         contents.
"""

import os
import re
import logging
import contextlib
from pathlib import Path
from pepclibs.helperlibs import YAML, ClassHelpers, FSHelpers, ProjectFiles
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

# Users can define this environment variable to extend the default spec files.
_SPECS_PATH_ENVVAR = "PEPC_TPMI_DATA_PATH"

_LOG = logging.getLogger()

def _find_spec_dirs():
    """Find paths to TPMI specs directories and return them as a list."""

    spec_dirs = []

    # Add the user-defined spec files directory. This directory is optional and can be used for
    # extending the standard spec files.
    path = os.getenv(_SPECS_PATH_ENVVAR)
    if path:
        path = Path(path)
        if not path.exists():
            _LOG.warning("TPMI spec files path '%s' specified in the '%s' environment "
                         "variable does not exist, ignoring it", path, _SPECS_PATH_ENVVAR)
        else:
            spec_dirs.append(path)

    # Find the standard spec-files.
    spec_dirs.append(ProjectFiles.find_project_data("pepc", "tpmi", what="TPMI spec files"))

    return spec_dirs

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

    def get_features(self):
        """
        Parse and return a tuple of two lists for TPMI features for the platform. First list
        contains the fully supported features, meaning features that have both spec files and
        hardware support available. The second list contains the features that are available on
        hardware, but there are no spec files available for them.
        """

        avail_features = set()

        for dirname, _, _ in self._pman.lsdir(self._tpmi_pci_paths[0]):
            match = re.match(r"^tpmi-id-([0-9a-f]+)$", dirname)
            if match:
                avail_features.add(int(match.group(1), 16))

        supported_features = {}
        for fname, fid in self._get_supported_fnames_and_fids():
            supported_features[fid] = fname

        supported = []
        missing = []

        for fid in avail_features:
            if fid in supported_features:
                supported.append(supported_features[fid])
            else:
                missing.append(fid)

        missing.sort()

        return (supported, list(map(hex, missing)))

    def _get_debugfs_tpmi_dirs(self):
        """
        Scan the debugfs root directory for TPMI-related sub-directories and return their paths in
        the form of a list.
        """

        debugfs_tpmi_dirs = []
        for dirname, path, _ in self._pman.lsdir(self._debugfs_mnt):
            if dirname.startswith("tpmi-"):
                debugfs_tpmi_dirs.append(path)

        if debugfs_tpmi_dirs:
            return debugfs_tpmi_dirs

        raise ErrorNotSupported(f"No TPMI-related sub-directories fount in '{self._debugfs_mnt}'"
                                f"{self._pman.hostmsg}.\nTPMI does not appear to be supported "
                                f"'{self._pman.hostmsg}. Here are the possible reasons:\n"
                                f" 1. Hardware does not support TPMI.\n"
                                f" 2. The kernel is old and doesn't have the TPMI driver. TPMI "
                                f" support was added in kernel version 6.6.\n"
                                f" 3. The TPMI driver is not enabled. Try to compile the kernel "
                                f"with 'CONFIG_INTEL_TPMI' enabled.\n")

    def __init__(self, pman, spec_dirs=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * spec_dirs - a collection of spec file directory paths on the target host to look for
                        spec files in (auto-detect by default).
        """

        self._spec_dirs = spec_dirs
        self._pman = pman

        # The feature dictionaries cache, indexed by feature name.
        self._fdict_cache = {}
        # The debugfs mount point.
        self._debugfs_mnt = None
        # Whether debugfs should be unmounted on 'close()'.
        self._unmount_debugfs = None
        # TPMI-related sub-directories in 'self._debugfs_mnt' (one per TPMI PCI device).
        self._tpmi_pci_paths = None

        if not self._spec_dirs:
            self._spec_dirs = _find_spec_dirs()

        self._debugfs_mnt, self._unmount_debugfs = FSHelpers.mount_debugfs(pman=self._pman)
        self._tpmi_pci_paths = self._get_debugfs_tpmi_dirs()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_unmount_debugfs", None):
            with contextlib.suppress(Error):
                self._pman.run(f"unmount {self._debugfs_mnt}")

        ClassHelpers.close(self, unref_attrs=("_pman",))
