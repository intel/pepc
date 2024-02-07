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

  * supported feature - a TPMI feature supported by the processor.

  * known feature - a supported feature for which the spec file was found, so that the feature can
                    be decoded and used.

  * unknown feature - a supported feature for which the spec file was not found.
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

    def _scan_spec_dirs(self):
        """
        Scan the spec file directories an yield a "scan_info" dictionary for every known feature.
        Scan dictionaries include basic feature information, such as name, feature ID and
        description.

        Note, this method ends up loading all spec files, so it may be expensive.
        """

        if not self._fdict_cache:
            for spec_dir in self._spec_dirs:
                for specname in os.listdir(spec_dir):
                    match = re.match(r"^(.*).yaml", specname)
                    if match:
                        fname = match.group(1)
                        fdict = YAML.load(spec_dir / specname)
                        self._fdict_cache[fname] = fdict

        for fdict in self._fdict_cache.values():
            scan_info = {}
            scan_info["name"] = fdict["name"]
            scan_info["desc"] = fdict["desc"].rstrip()
            scan_info["feature-id"] = fdict["feature-id"]
            yield scan_info

    def list_features(self):
        """
        Detect the list of features supported by the target platform, scan the spec file directories
        and detect the list of available spec files, and return a tuple of two lists:
        '(known_fnames, unknown_fids)'.
        The lists are as follows.
          * known - a list of "scan_info" dictionaries for every known feature (supported and have
                    the spec file).
          * unknown - a list of feature IDs for every unknown feature (supported, but no spec file
                      found).

        The "scan_info" dictionaries include the following keys.
          * name - feature name.
          * desc - feature description.
          * feature-id - an integer feature ID.
        """

        supported_fids = set()

        for dirname, _, _ in self._pman.lsdir(self._tpmi_pci_paths[0]):
            match = re.match(r"^tpmi-id-([0-9a-f]+)$", dirname)
            if match:
                supported_fids.add(int(match.group(1), 16))

        scan_infos = {}
        for scan_info in self._scan_spec_dirs():
            scan_infos[scan_info["feature-id"]] = scan_info

        known = []
        unknown = []

        for fid in supported_fids:
            if fid in scan_infos:
                known.append(scan_infos[fid])
            else:
                unknown.append(fid)

        unknown.sort()

        return (known, list(map(hex, unknown)))

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
