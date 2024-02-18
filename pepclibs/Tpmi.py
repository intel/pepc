# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""
Provide capability for reading and writing TPMI registers on Intel CPUs. TPMI stands for "Topology
Aware Register and PM Capsule Interface" and it is a  memory mapped interface for accessing power
management features on Intel CPUs, in addition to the existing MSRs.

Terminology.
  * feature - a group of TPMI registers exposed by the processor via PCIe VSEC (Vendor-Specific
              Extended Capabilities) as a single capability. Typically TPMI feature corresponds to
              a real processor feature. For example, "uncore" TPMI feature includes processor
              registers related to uncore frequency scaling. The "rapl" TPMI feature includes
              processor registers related to processor's Running Average Power Limit (RAPL) feature.
              The "sst" feature includes processor registers related to Intel Speed Select
              Technology (SST) feature.

  * supported feature - a TPMI feature supported by the processor.

  * known feature - a supported feature for which the spec file was found, so that the feature can
                    be decoded and used.

  * unknown feature - a supported feature for which the spec file was not found.

  * feature ID - a unique integer number assigned to a feature.

  * feature dictionary - a dictionary describing a TPMI feature registers, bit fields and other
                         details. Feature dictionary is formed based on the feature spec file
                         contents.

  * feature map - a dictionary that maps known feature names to corresponding debugfs file paths on
                  the target host. This data structure is built by scanning the TPMI debugfs
                  hierarchy of the target host.

  * spec file - a YAML file describing the registers and bitfields for a TPMI feature. Each
                supported feature has a spec file, and each spec file corresponds to a feature. A
                spec file is also required to decode the TPMI feature's PCIe VSEC table.

  * spec directory - a directory containing one or multiple spec files. There may be multiple spec
                     directories.

  * spec dictionary - a dictionary including basic TPMI spec file information - name, ID, and
                      description of the feature it describes, path to the spec file. Spec
                      dictionaries are built by partially reading the spec file during the initial
                      scanning of spec directories.

  * instance - TPMI features often consist of logical "areas" or "components", which are feature-
               specific. For example, the "rapl" TPMI feature includes package, power, memory, and
               other RAPL domains. These logical components are represented by TPMI instances, which
               are just integer numbers. In order to read/write a TPMI register, one has to specify
               the instance for the read/write operation.

  * mem_dump - a Linux TPMI debugfs file named "mem_dump" (example path:
               /sys/kernel/debug/tpmi-0000:00:03.1/tpmi-id-00/mem_dump). The 'mem_dump' files
               provide TPMI memory dump a in text format. The 'mem_dump' file includes TPMI memory
               dump for all instances. TPMI register read operations are performed by reading from
               the 'mem_dump' file. This requires finding the 'mem_dump' file position to read from,
               which, in turn, requires parsing the 'mem_dump' file.

  * mdmap - mem_dump map, a dictionary representing a 'mem_dump' file. The role of mdmap is to avoid
    parsing 'mem_dump' on every TPMI register read. Mdmap is a 2-level dictionary. The first level
    is indexed by the instance number, the second level is indexed with TPMI memory offset, with
    values being 'mem_dump' file position. In other words, for a given instance number and TPMI
    register offset, mdmap gives 'mem_dump' file position. Reading from this position or writing to
    it ends up with reading from or writing to the TPMI register.

  * offset - in this module word "offset" is used to refer to TPMI register offsets, which are
             defined in spec files.

  * position - in this module word "position" is used to refer to a file position relative to the
               beginning of the file (e.g., a 'mem_dump' file position). See the standard Unix
               'fsetpos()' method for more information about a file position.
"""

import os
import re
import stat
import logging
import contextlib
from pathlib import Path
import yaml
from pepclibs.helperlibs import YAML, ClassHelpers, FSHelpers, ProjectFiles, Trivial, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

# Users can define this environment variable to extend the default spec files.
_SPECS_PATH_ENVVAR = "PEPC_TPMI_DATA_PATH"

# Maximum count of spec files per directory.
_MAX_SPEC_FILES = 256
# Maximum count of non-YAML files (extention is other than '.yml' or '.yaml') per directory.
_MAX_NON_YAML = 32
# Maximum count of spec file loading/parsing errors during scanning per spec directory.
_MAX_SCAN_LOAD_ERRORS = 4
# Maximum spec file size in bytes.
_MAX_SPEC_FILE_BYTES = 4 * 1024 * 1024 * 1024

_LOG = logging.getLogger()

def _find_spec_dirs():
    """Find paths to TPMI spec directories and return them as a list."""

    specdirs = []

    # Add the user-defined spec directory. This directory is optional and can be used for extending
    # the standard spec files.
    path = os.getenv(_SPECS_PATH_ENVVAR)
    if path:
        path = Path(path)
        if not path.exists():
            _LOG.warning("TPMI spec files path '%s' specified in the '%s' environment "
                         "variable does not exist, ignoring it", path, _SPECS_PATH_ENVVAR)
        else:
            specdirs.append(path)

    # Find the standard spec-files.
    specdirs.append(ProjectFiles.find_project_data("pepc", "tpmi", what="TPMI spec files"))

    return specdirs

def _load_sdict(specpath):
    """
    Partially load spec file at 'specpath', just enough to get feature name, description, and ID.
    Create and return the spec dictionary for the spec file.

    The implementation is optimized to avoid loading the entire spec file and instead, only look at
    the beginning of the file.
    """

    fobj = None

    # Basic spec file validation.
    try:
        st = specpath.stat()
    except OSError as err:
        msg = Error(str(err)).indent(2)
        raise Error(f"failed to open spec file '{specpath}:\n{msg}") from err

    if st.st_size > _MAX_SPEC_FILE_BYTES:
        maxsize = Human.bytesize(_MAX_SPEC_FILE_BYTES)
        raise Error(f"too large spec file '{specpath}', maximum allow size is {maxsize}")

    if not stat.S_ISREG(st.st_mode):
        raise Error(f"'{specpath}' is not a regular file")

    try:
        try:
            fobj = open(specpath, "r", encoding="utf-8") # pylint: disable=consider-using-with
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"failed to open spec file '{specpath}:\n{msg}") from err

        loader = yaml.SafeLoader(fobj)
        event = None
        while True:
            event = loader.peek_event()
            if not event:
                raise Error("bad spec file '{specpath}': 'feature-id' key was not found")
            if isinstance(event, yaml.ScalarEvent):
                break
            loader.get_event()

        # The first 3 keys must be: name, desc, and feature-id.
        valid_keys = {"name", "desc", "feature-id"}
        left_keys = set(valid_keys)
        sdict = {}
        while len(sdict) < len(valid_keys):
            event = loader.get_event()
            if not event:
                keys = ", ".join(left_keys)
                raise Error(f"bad spec file '{specpath}': missing keys '{keys}'")

            key = str(event.value)
            if key not in valid_keys:
                raise Error(f"bad spec file '{specpath}' format: the first 3 keys must be "
                            f"'name', 'desc', and 'feature-id', got key '{key}' instead")
            if key in sdict:
                raise Error("bad spec file '{specpath}': repeating key '{key}'")

            event = loader.get_event()
            if not event:
                raise Error("bad spec file '{specpath}': no value for key '{key}'")

            if key == "feature-id":
                value = Trivial.str_to_int(event.value, what="'feature-id' key value")
            else:
                value = str(event.value)
            sdict[key] = value
            left_keys.remove(key)
    finally:
        if fobj:
            fobj.close()

    sdict["path"] = specpath
    return sdict

class Tpmi():
    """
    Provide API for reading and writing TPMI registers on Intel CPUs.

    Public methods overview.

    1. Getting features information.
        * 'get_known_features()' - known features information.
        * 'get_unknown_features()' - unknown features information.
    """

    def _get_fdict(self, fname):
        """
        Return the feature dictionary feature 'fname'. If the dictionary is not available in the
        cache, loaded it from the spec file.
        """

        if fname in self._fdict_cache:
            return self._fdict_cache[fname]

        for specdir in self._specdirs:
            specpath = specdir / (fname + ".yml")
            if specpath.exists():
                spec = YAML.load(specpath)
                self._fdict_cache[fname] = spec

        if fname not in self._fdict_cache:
            raise ErrorNotSupported(f"TPMI feature '{fname}' is not supported")

        return self._fdict_cache[fname]

    def get_known_features(self):
        """
        Return a list of spec dictionaries for all known features (features that are supported by the
        target host and there is a spec file available). The spec dictionary includes the following
        keys.
          * name - feature name.
          * desc - feature description.
          * feature-id - an integer feature ID.
          * path - path to the spec file of the feature.
        """

        known = []
        for fname in self._fmap:
            known.append(self._sdicts[fname].copy())
        return known

    def get_unknown_features(self):
        """
        Return a list of feature IDs for all unknown features (features that are supported by the
        target host and there is no spec file available).
        """

        return list(self._unknown_fids)

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

        raise ErrorNotSupported(f"no TPMI-related sub-directories found in '{self._debugfs_mnt}'"
                                f"{self._pman.hostmsg}.\nTPMI does not appear to be supported "
                                f"'{self._pman.hostmsg}. Here are the possible reasons:\n"
                                f" 1. Hardware does not support TPMI.\n"
                                f" 2. The kernel is old and doesn't have the TPMI driver. TPMI "
                                f" support was added in kernel version 6.6.\n"
                                f" 3. The TPMI driver is not enabled. Try to compile the kernel "
                                f"with 'CONFIG_INTEL_TPMI' enabled.\n")

    def _build_sdicts(self):
        """Scan the spec directories and build the spec dictionaries."""

        sdicts = {}
        for specdir in self._specdirs:
            spec_files_cnt = 0
            non_yaml_cnt = 0
            load_errors_cnt = 0

            for specname in os.listdir(specdir):
                if not specname.endswith(".yml") and not specname.endswith(".yaml"):
                    non_yaml_cnt += 1
                    if non_yaml_cnt > _MAX_NON_YAML:
                        raise Error(f"too many non-YAML files in '{specdir}', maximum allowed "
                                    f"count is {_MAX_NON_YAML}")
                    continue

                try:
                    specpath = specdir / specname
                    sdict = _load_sdict(specpath)
                except Error as err:
                    load_errors_cnt += 1
                    if load_errors_cnt > _MAX_SCAN_LOAD_ERRORS:
                        raise Error(f"failed to load spec file '{specpath}':\n{err.indent(2)}\n"
                                    f"Reached the maximum spec file load errors count of "
                                    f"{_MAX_SCAN_LOAD_ERRORS}") from err
                    continue

                spec_files_cnt += 1
                if spec_files_cnt > _MAX_SPEC_FILES:
                    raise Error(f"too many spec files in '{specdir}, maximum allowed spec files "
                                f"count is {_MAX_SPEC_FILES}")

                sdicts[sdict["name"]] = sdict

        if not sdicts:
            paths = "\n * ".join([str(path) for path in self._specdirs])
            raise ErrorNotSupported(f"no TPMI spec files found, checked the following paths:\n"
                                    f" * {paths}")

        self._sdicts = sdicts
        for fname, sdict in sdicts.items():
            self._fid2fname[sdict["feature-id"]] = fname

    def _build_features_map(self):
        """Build the TPMI feature map."""

        # A dictionary mapping feature IDs to debugfs paths corresponding to the feature.
        fid2paths = {}
        for pci_path in self._tpmi_pci_paths:
            for dirname, dirpath, _ in self._pman.lsdir(pci_path):
                match = re.match(r"^tpmi-id-([0-9a-f]+)$", dirname)
                if not match:
                    continue

                fid = int(match.group(1), 16)
                if fid not in fid2paths:
                    fid2paths[fid] = []

                fid2paths[fid].append(dirpath)

        if not fid2paths:
            paths = "\n * ".join([str(path) for path in self._tpmi_pci_paths])
            raise ErrorNotSupported(f"no TPMI features found{self._pman.hostmsg}, checked the "
                                    f"following paths:\n * {paths}")

        fmap = {}
        unknown_fids = []

        for fid, fpaths in fid2paths.items():
            fname = self._fid2fname.get(fid)
            if not fname:
                # Unknown feature, no spec file for it.
                unknown_fids.append(fid)
                continue

            if fname not in fmap:
                fmap[fname] = {}
            fmap[fname] = fpaths

        self._fmap = fmap
        self._unknown_fids = unknown_fids

    def _get_debugfs_feature_path(self, addr, fname):
        """
        Return path to the Linux debugfs directory represinting feature 'fname' of a TPMI device at
        address 'addr'.
        """

        path = self._debugfs_mnt / f"tpmi-{addr}"
        fid = self._get_fdict(fname)["feature-id"]
        path = path / f"tpmi-id-{fid:02x}"

        return path

    def _build_mdmap(self, addr, fname):
        """
        Build and return mdmap for feature 'fname' of TPMI device at address 'addr'. The arguments
        are as follows.
          * addr - TPMI device PCI address to build the mdmap for.
          * fname - TPMI feature name.

        Here is an example of mdmap for a TPMI feature with two instances (0 and 1) and 4 TPMI
        register offsets in each instance.
          {0: {0: 48, 4: 57, 8: 66, 12: 75},
           1: {0: 77, 4: 86, 8: 95, 12: 104}}.
        In this example, in order to read from register with offset 8 in instance 1, one has to read
        from position 95 of the corresponding 'mem_dump' Linux debugfs file.
        """

        path = self._get_debugfs_feature_path(addr, fname)
        path = path / "mem_dump"

        _LOG.debug("reading memory dump: '%s'", path)

        mdmap = {}
        offset = 0

        with self._pman.open(path, "r") as fobj:
            for line in fobj:
                line = line.rstrip()
                line_offset = 0

                # Sample line to match: "TPMI Instance:1 offset:0x40005000".
                match = re.match(r"TPMI Instance:(\d+) offset:(0x[0-9a-f]+)", line)
                if match:
                    instance = Trivial.str_to_int(match.group(1), what="instance number")
                    mdmap[instance] = {}

                # Matches two different line formats:
                #   " 00000020: 013afd40 00004000 2244aacc deadbeef" and
                #   "[00000020] 013afd40 00004000 2244aacc deadbeef".
                # Some older kernels have the second format in place.
                match = re.match(r"^( |\[)([0-9a-f]+)(:|\]) (.*)$", line)
                if match:
                    memaddr = Trivial.str_to_int(match.group(2), base=16, what="TPMI offset")
                    data_arr = Trivial.split_csv_line(match.group(4), sep=" ")
                    line_offset += 3 + len(match.group(2))
                    for data_val in data_arr:
                        # Just verify the value.
                        Trivial.str_to_int(data_val, base=16, what="TPMI value")
                        mdmap[instance][memaddr] = offset + line_offset
                        line_offset += 9
                        memaddr += 4

                offset += len(line) + 1

        return mdmap

    def __init__(self, pman, specdirs=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * specdirs - a collection of spec directory paths on the target host to look for spec
                       files in (auto-detect by default).
        """

        self._specdirs = specdirs
        self._pman = pman

        # The feature dictionaries cache, indexed by feature name.
        self._fdict_cache = {}
        # The debugfs mount point.
        self._debugfs_mnt = None
        # Whether debugfs should be unmounted on 'close()'.
        self._unmount_debugfs = None
        # TPMI-related sub-directories in 'self._debugfs_mnt' (one per TPMI PCI device).
        self._tpmi_pci_paths = None
        # Spec files "sdict" dictionaries for every supported feature.
        self._sdicts = None
        # The feature ID -> feature name dictionary (supported features only).
        self._fid2fname = {}
        # The features map.
        self._fmap = None
        # Unknown feature IDs (no spec file).
        self._unknown_fids = None

        if not self._specdirs:
            self._specdirs = _find_spec_dirs()

        # Keep absolute paths to spec directories - in case of an error a directory path like 'tpmi'
        # may look confusing comparint to a path like '/my/path/tpmi'.
        specdirs = self._specdirs
        self._specdirs = []
        for specdir in specdirs:
            self._specdirs.append(Path(specdir).resolve().absolute())

        self._debugfs_mnt, self._unmount_debugfs = FSHelpers.mount_debugfs(pman=self._pman)
        self._tpmi_pci_paths = self._get_debugfs_tpmi_dirs()

        self._build_sdicts()
        self._build_features_map()

    def close(self):
        """Uninitialize the class object."""

        if self._unmount_debugfs:
            with contextlib.suppress(Error):
                self._pman.run(f"unmount {self._debugfs_mnt}")

        ClassHelpers.close(self, unref_attrs=("_pman",))
