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

Naming convention/logic:
   * something dict - a dictionary describing something, and it contains information from the spec
                      file.
   * something map - a dictionary describing something, and it contains information from the debugfs
                     files and directories.

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

  * fdict - feature dictionary, a dictionary describing a TPMI feature registers, bit fields and
            other details. Fdict contents is corresponds to the feature spec file contents under the
            "registers" key. Fdict keys are register names, and values are regdister dictionaries
            (regdicts). The parts of the spec file outside of the 'registers' key are stored in the
            sdict.

  * regdict - register dictionary, a sub-dictionary of fdict describing a single register.

  * fmap - feature map, a dictionary providing TPMI device PCI addresses and debugfs file paths
           corresponging to the feature.

  * spec file - a YAML file describing the registers and bit fields for a TPMI feature. Each
                supported feature has a spec file, and each spec file corresponds to a feature. A
                spec file is also required to decode the TPMI feature's PCIe VSEC table.

  * spec directory - a directory containing one or multiple spec files. There may be multiple spec
                     directories.

  * sdict - spec file dictionary, a dictionary including basic TPMI spec file information - name,
            ID, and description of the feature it describes, path to the spec file. Spec
            dictionaries are built by partially reading the spec file during the initial scanning of
            spec directories.

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
            parsing 'mem_dump' on every TPMI register read. Mdmap is a 2-level dictionary. The first
            level is indexed by the instance number, the second level is indexed with TPMI memory
            offset, with values being 'mem_dump' file position. In other words, for a given instance
            number and TPMI register offset, mdmap gives 'mem_dump' file position. Reading from this
            position results in reading from the TPMI register.

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

    def _format_fdict(self, fname, specpath, spec):
        """
        Vaildate a the 'spec' dictionary correspoonding to a spec file of feature 'fname', build and
        return the corresponding fdict.

        Note, this method modifies the 'spec' dictionary in-place, in order to avoid a costly
        'spec["registers"]' copy operation.

        Mangle the fdict by adding "bitshift" and "bitmask" keys.
        """

        def _raise_exc(msg):
            """Raise an exception with message 'msg'."""

            pfx = f"bad '{fname}' spec file '{specpath}'"
            raise Error(f"{pfx}:\n{Error(msg).indent(2)}")

        def _check_keys(check_dict, allowed_keys, mandatory_keys, where):
            """
            Check keys of dictionary 'check_dict', verify the following.
            * The dictionary keys are in 'allowed_keys'.
            * The dictionary has 'mandatory_keys' keys.
            """

            for key in check_dict:
                if key not in allowed_keys:
                    allowed_keys = ", ".join(allowed_keys)
                    _raise_exc(f"unexpected key '{key}' {where}, allowed keys are: {allowed_keys}")

            for key in mandatory_keys:
                if key not in check_dict:
                    mandatory_keys = ", ".join(mandatory_keys)
                    _raise_exc(f"missing key '{key}' {where}, mandatory keys are: {mandatory_keys}")

        if "registers" not in spec:
            _raise_exc("the 'registers' top-level key was not found")

        # The allowed and the mandatory top-level key names.
        keys = {"name", "desc", "feature-id", "registers"}
        where = "at the top level of the spec file"
        _check_keys(spec, keys, keys, where)

        fdict = spec["registers"]
        for regname, regdict in fdict.items():
            if not regname.isupper():
                _raise_exc(f"bad TPMI register name '{regname}': should include only upper case "
                           f"characters")

            # The allowed and the mandatory regdict key names.
            keys = {"fields", "offset", "width"}
            where = f"in the '{regname}' TPMI register definition"
            _check_keys(regdict, keys, keys, where)

            # Validate the offset.
            offset = regdict["offset"]
            if not isinstance(offset, int):
                _raise_exc(f"bad offset '{offset}' in TPMI register '{regname}': must be an "
                           f"integer")
            if offset % 4:
                _raise_exc(f"bad offset '{offset}' in TPMI register '{regname}': must be multiple "
                           f"of 4 bytes")

            # Validate the width.
            width = regdict["width"]
            if not isinstance(width, int):
                _raise_exc(f"bad width '{width}' in TPMI register '{regname}': must be an "
                           f"integer")
            if width not in (32, 64):
                _raise_exc(f"bad width '{width}' in TPMI register '{regname}': must be either 32 "
                           f"or 64")

            for bfname, bitdict in regdict["fields"].items():
                if not bfname.isupper():
                    _raise_exc(f"bad bit field name '{bfname}' for TPMI register '{regname}': "
                               f"should include only upper case characters")

                # The allowed and the mandatory bit field dictionary key names.
                keys = {"bits", "desc"}
                where = f"in bit field '{bfname}' of the '{regname}' TPMI register definition"
                _check_keys(bitdict, keys, keys, where)

                # Make sure that the description has no newline character.
                if "\n" in bitdict["desc"]:
                    _raise_exc(f"bad description of bit field '{bfname}' of the '{regname}' TPMI "
                               f"register: includes a newline character")

                # Verify the bits and add "bitshift" and "bitmask".
                where = f"in bit field '{bfname}' of the '{regname}' TPMI register"
                bits = Trivial.split_csv_line(bitdict["bits"], sep=":")
                if len(bits) != 2:
                    bits = bitdict["bits"]
                    _raise_exc(f"bad 'bits' key value '{bits}' {where}: should have the "
                               f"'<high-bit>:<low-bit>' format")

                what = f"the '%s' value {where}"
                highbit = Trivial.str_to_int(bits[0], what=what % bits[0])
                lowbit = Trivial.str_to_int(bits[1], what=what % bits[1])

                if highbit < lowbit:
                    bits = bitdict["bits"]
                    _raise_exc(f"bad 'bits' key value '{bits}' {where}: high bit value '{highbit}' "
                               f"is smaller than low bit value '{lowbit}'")

                bitmask = ((1 << (highbit + 1)) - 1) - ((1 << lowbit) - 1)
                bitdict["bitshift"] = lowbit
                bitdict["bitmask"] = bitmask

        return fdict

    def _get_fdict(self, fname):
        """
        Return fdict for feature 'fname'. If the fdict is not available in the cache, loaded it from
        the spec file.
        """

        if fname in self._fdicts:
            return self._fdicts[fname]

        for specdir in self._specdirs:
            specpath = specdir / (fname + ".yml")
            if specpath.exists():
                spec = YAML.load(specpath)
                self._fdicts[fname] = self._format_fdict(fname, specpath, spec)

        if fname not in self._fdicts:
            raise ErrorNotSupported(f"TPMI feature '{fname}' is not supported")

        return self._fdicts[fname]

    def _get_sdict(self, fname):
        """Return sdict for feature 'fname'."""

        sdict = self._sdicts.get(fname)
        if sdict is None:
            known = ", ".join(self._sdicts)
            raise Error(f"unknown feature '{fname}'{self._pman.hostname}, known features are: "
                        f"{known}")

        return sdict

    def get_known_features(self):
        """
        Return a list of spec dictionaries for all known features (features that are supported by
        the target host and there is a spec file available). The spec dictionary includes the
        following keys.
          * name - feature name.
          * desc - feature description.
          * feature-id - an integer feature ID.
          * path - path to the spec file of the feature.
        """

        known = []
        for fname in self._fmaps[0]:
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

    def _build_fmaps(self):
        """
        Build fmap skeletons for every known TPMI feature and save the result in 'self._fmaps'.

        The structure of the 'self._fmaps' dictionary is as follows.
          - First level key - package number
          - Second level key - feature name
          - Third level key - PCI address of the TPMI device
          - Value - the mdmap of the feature.
        """

        # A dictionary mapping feature names to the list of TPMI device addresses that provide this
        # feature.
        fname2addrs = {}
        # List of unknown feature IDs.
        unknown_fids = []

        for pci_path in self._tpmi_pci_paths:
            for dirname, _, _ in self._pman.lsdir(pci_path):
                match = re.match(r"^tpmi-id-([0-9a-f]+)$", dirname)
                if not match:
                    continue

                fid = int(match.group(1), 16)
                fname = self._fid2fname.get(fid)
                if not fname:
                    # Unknown feature, no spec file for it.
                    unknown_fids.append(fid)
                    continue

                if fname not in fname2addrs:
                    fname2addrs[fname] = []

                addr = pci_path.name[len("tpmi-"):]
                fname2addrs[fname].append(addr)

        if not fname2addrs:
            paths = "\n * ".join([str(path) for path in self._tpmi_pci_paths])
            raise ErrorNotSupported(f"no TPMI features found{self._pman.hostmsg}, checked the "
                                    f"following paths:\n * {paths}")

        if "tpmi_info" not in fname2addrs:
            dirs = "\n * ".join([str(path) for path in self._specdirs])
            raise Error(f"spec file for the 'tpmi_info' TPMI feature was not found, checked in the "
                        f"following directories:\n * {dirs}")

        addr2pkg = {}
        fmaps = {}

        for fname, addrs in fname2addrs.items():
            for addr in addrs:
                if addr not in addr2pkg:
                    mdmap = self._build_mdmap(addr, "tpmi_info")
                    package = self._read_register(addr, "tpmi_info", 0, "TPMI_BUS_INFO",
                                                  bfname="PACKAGE_ID", mdmap=mdmap)
                    addr2pkg[addr] = package

                    if package not in fmaps:
                        fmaps[package] = {}
                    if "tpmi_info" not in fmaps[package]:
                        fmaps[package]["tpmi_info"] = {}

                    fmaps[package]["tpmi_info"][addr] = mdmap
                else:
                    package = addr2pkg[addr]

                if fname not in fmaps[package]:
                    fmaps[package][fname] = {}

                if fname != "tpmi_info":
                    fmaps[package][fname][addr] = None

        self._fmaps = fmaps
        self._unknown_fids = unknown_fids

    def _get_debugfs_feature_path(self, addr, fname):
        """
        Return path to the Linux debugfs directory represinting feature 'fname' of a TPMI device at
        address 'addr'.
        """

        path = self._debugfs_mnt / f"tpmi-{addr}"
        fid = self._get_sdict(fname)["feature-id"]
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

        _LOG.debug("reading 'mem_dump' file at '%s'", path)

        mdmap = {}
        pos = 0

        with self._pman.open(path, "r") as fobj:
            for line in fobj:
                line = line.rstrip()
                line_pos = 0

                # Sample line to match: "TPMI Instance:1 offset:0x40005000".
                match = re.match(r"TPMI Instance:(\d+) offset:(0x[0-9a-f]+)", line)
                if match:
                    instance = Trivial.str_to_int(match.group(1), what="instance number")
                    mdmap[instance] = {}
                else:
                    # Matches two different line formats:
                    #   " 00000020: 013afd40 00004000 2244aacc deadbeef" and
                    #   "[00000020] 013afd40 00004000 2244aacc deadbeef".
                    # Some older kernels have the second format in place.
                    match = re.match(r"^( |\[)([0-9a-f]+)(:|\]) (.*)$", line)
                    if match:
                        offs = Trivial.str_to_int(match.group(2), base=16, what="TPMI offset")
                        regvals = Trivial.split_csv_line(match.group(4), sep=" ")
                        line_pos += 3 + len(match.group(2))
                        for regval in regvals:
                            # Sanity-check register values and drop them.
                            Trivial.str_to_int(regval, base=16, what="TPMI value")
                            mdmap[instance][offs] = pos + line_pos
                            line_pos += 9
                            offs += 4
                    else:
                        raise Error("unexpected line in {path}:\n{line}")

                pos += len(line) + 1

        return mdmap

    def _get_regdict(self, fname, regname):
        """Get regdict for TPMI register 'regname' of feature 'fname'."""

        fdict = self._get_fdict(fname)

        regdict = fdict.get(regname)
        if regdict is None:
            raise Error(f"BUG: bad register '{regname}' for feature {fname}")

        return fdict[regname]

    def _read(self, addr, fname, instance, offset, mdmap):
        """Read a TPMI register from the 'mem_dump' file."""

        # Feature and device.
        msg_fd = f"""feature '{fname}', for device '{addr}'"""
        # Instance, feature and device.
        msg_ifd = f"""instance '{instance}', {msg_fd}"""

        if instance not in mdmap:
            available = Human.rangify(mdmap)
            raise Error(f"bad instance number '{instance}' for {msg_fd}, available instances: "
                        f"{available}")

        if offset not in mdmap[instance]:
            max_offset = max(mdmap[instance])
            raise Error(f"bad offset '{offset:#x}' for {msg_ifd}, max. offset is '{max_offset}'")

        path = self._get_debugfs_feature_path(addr, fname)
        path = path / "mem_dump"

        with self._pman.open(path, "r") as fobj:
            fobj.seek(mdmap[instance][offset])
            val = fobj.read(8)

        what = f"value of a TPMI register at offset '{offset:#x}', {msg_ifd}"
        return Trivial.str_to_int(val, base=16, what=what)

    def _get_bitfield(self, regval, fname, regname, bfname):
        """
        Extract and return the value of a bit field from a register value. The arguments are as
        follows.
          * regval - value of the register.
          * fname - name of the TPMI feature.
          * regname - name of the TPMI register.
          * bfname - name of the TPMI register bit field to extract.
        """

        regdict = self._get_regdict(fname, regname)
        fieldsdict = regdict["fields"]

        if bfname not in fieldsdict:
            available = ", ".join(fieldsdict)
            raise Error(f"bit field '{bfname}' not found for TPMI register '{regname}', feature "
                        f"'{fname}', available bit fields: {available}")

        bitdict = fieldsdict[bfname]
        return (regval & bitdict["bitmask"]) >> bitdict["bitshift"]

    def _read_register(self, addr, fname, instance, regname, bfname=None, mdmap=None):
        """
        Read a TPMI register. The arguments are as follows.
          * addr - the TPMI device address.
          * fname - name of the TPMI feature the register belongs to.
          * instance - the TPMI instance to read the register from.
          * regname - name of the TPMI register to read.
          * bfname - bit field name to read (read whole register by default).
          * mdmap - the mdmap to use fro reading the register.
        """

        regname = regname.upper()
        regdict = self._get_regdict(fname, regname)

        offset = regdict["offset"]
        width = regdict["width"]

        if not mdmap:
            mdmap = self._build_mdmap(addr, fname)

        val = self._read(addr, fname, instance, offset, mdmap)
        if width > 32:
            val = val + (self._read(addr, fname, instance, offset + 4, mdmap) << 32)

        if bfname:
            val = self._get_bitfield(val, fname, regname, bfname)

        return val

    def _get_mdmap(self, addr, package, fname):
        """Get mdmap for a TPMI feature."""

        mdmap = self._fmaps[package][fname][addr]
        if not mdmap:
            mdmap = self._build_mdmap(addr, fname)
            self._fmaps[package][fname][addr] = mdmap

        return mdmap

    def _fmap_lookup(self, fname, instance, addr=None, package=None):
        """
        Search for a TPMI feature instance in the fmap. If found, return the following tuple for the
        matching TPMI device: '(addr, mdmap)'.
          - addr - PCI address of the matching TPMI device.
          - mdmap - mdmap of the matching instance.
        """

        def _format_addrs(addrs):
            """Format a list of TPMI device PCI addresses in form of a string."""

            max_addrs = 8
            if len(addrs) > max_addrs:
                # The list of addresses may potentially be long, limit it.
                addrs = list(addrs)[:max_addrs]
                addrs.append("... and more ...")
            return "\n * ".join(addrs)

        if package is None and addr is None:
            raise Error("either package or TPMI device PCI address must be provided")

        if package is None:
            addrs = set()
            for pkg, fmap in self._fmaps.items():
                addrs.update(list(fmap[fname]))
                if addr in fmap[fname]:
                    package = pkg
                    break
            if package is None:
                addrs = _format_addrs(addrs)
                raise Error(f"unavailable TPMI device '{addr}' for feature '{fname}'"
                            f"{self._pman.hostmsg}, available devices are:\n * {addrs}")
        elif package not in self._fmaps:
            available = Human.rangify(self._fmaps)
            raise Error(f"invalid package number '{package}'{self._pman.hostmsg}, valid"
                        f"package numbers are: {available}")

        if addr is None:
            addrs = list(self._fmaps[package][fname])
            if len(addrs) == 1:
                addr = addrs[0]
            else:
                addrs = []
                for try_addr in self._fmaps[package][fname]:
                    mdmap = self._get_mdmap(try_addr, package, fname)
                    if instance in mdmap:
                        addrs.append(try_addr)

                if len(addrs) > 1:
                    addrs = _format_addrs(addrs)
                    raise Error(f"feature '{fname}', package '{package}' and instance '{instance}' "
                                f"are not enough to identify the TPMI device.\n"
                                f"Provide one of the following TPMI device PCI addesses to resolve "
                                f"the ambiguity:\n * {addrs}")
                addr = addrs[0]

        if addr not in self._fmaps[package][fname]:
            available = ", ".join(self._fmaps[package][fname])
            raise Error(f"unavailable TPMI device '{addr}', available devices: {available}")

        if fname not in self._fmaps[package]:
            known = ", ".join(self._fmaps[package])
            raise Error(f"unknown feature '{fname}'{self._pman.hostmsg}, known features are: "
                        f"{known}")

        mdmap = self._get_mdmap(addr, package, fname)

        if instance in mdmap:
            return addr, mdmap

        available = Human.rangify(range(max(mdmap) + 1))
        raise Error(f"instance {instance} not available for feature {fname}"
                    f"{self._pman.hostmsg}, available instances: {available}")

    def read_register(self, fname, instance, regname, package=None, addr=None, bfname=None):
        """
        Read a TPMI register or a bit field of a TPMI register and return the result. The arguments
        are as follows.
          * fname - name of the TPMI feature to read.
          * package - optional package number.
          * regname - name of the TPMI register to read.
          * addr - optional TPM device PCI address.
          * instance - the TPMI instance number to read.
          * bfname - optional name of the bit field to read (read the entire register by default).
        """

        addr, mdmap = self._fmap_lookup(fname, instance, addr=addr, package=package)

        return self._read_register(addr, fname, instance, regname, mdmap=mdmap, bfname=bfname)

    def __init__(self, pman, specdirs=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * specdirs - a collection of spec directory paths on the target host to look for spec
                       files in (auto-detect by default).
        """

        self._specdirs = specdirs
        self._pman = pman

        # Feature dictionaries.
        self._fdicts = {}
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
        # Feature maps.
        self._fmaps = None
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
        self._build_fmaps()

    def close(self):
        """Uninitialize the class object."""

        if self._unmount_debugfs:
            with contextlib.suppress(Error):
                self._pman.run(f"unmount {self._debugfs_mnt}")

        ClassHelpers.close(self, unref_attrs=("_pman",))
