# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Enable reading and writing of TPMI registers on Intel CPUs. TPMI stands for "Topology Aware Register
and PM Capsule Interface" - a memory-mapped interface for accessing power management features on
Intel CPUs, supplementing the existing MSRs.

Terminology:
    * feature - A group of TPMI registers exposed by the processor via PCIe VSEC (Vendor-Specific
                Extended Capabilities) as a single capability. Typically, a TPMI feature corresponds
                to a processor capability. For example, the "uncore" TPMI feature includes registers
                for uncore frequency scaling, "rapl" covers Running Average Power Limit (RAPL), and
                "sst" covers Intel Speed Select Technology (SST).
    * supported feature - A TPMI feature available on the processor.
    * known feature - A supported feature with a corresponding spec file, allowing decoding and
                      usage.
    * unknown feature - A supported feature without a spec file.
    * feature ID - A unique integer identifier for a feature.
    * fdict - A dictionary describing TPMI registers associated with a feature. The fdict structure
              matches the "registers" section of the feature spec file. Keys are register names.
              Values are register dictionaries (regdicts). Information outside "registers" is stored
              in the sdict.
    * regdict - Register dictionary describing a single register within fdict.
    * bfdict - Bit field dictionary describing a single bit field within regdict.
    * spec file - YAML file describing the registers and bit fields for a TPMI feature. Each
                  supported feature has a spec file, which is also required to decode the feature's
                  PCIe VSEC table.
    * spec directory - Directory containing spec files. There is an 'index.yml' file in the spec
                       spec-directory, and sub-directories containing spec files for specific
                       platforms.
    * sdict - Spec file dictionary containing basic TPMI spec file information: feature name, ID,
              description, and spec file path. Sdicts are built by partially reading spec files
              during initial scanning.
    * instance - Logical "areas" or "components" within TPMI features, represented by integer
                 instance numbers. Specify the instance when reading or writing TPMI registers.
    * offset - TPMI register offset, as defined in spec files.
"""

# Internal terms (not exposed to users of this module).
#
# Naming conventions:
#   * something dict - Dictionary describing an object, populated from the spec file.
#   * something map - Dictionary describing an object, populated from debugfs files and directories.
#
# Terminology:
#   * fmap - Feature map. Maps PCI addresses to TPMI device information for a feature.
#            Example fmap structure:
#                {
#                  "0000:00:03.1": {"package": 0, "mdmap": mdmap},
#                  "0000:80:03.1": {"package": 1, "mdmap": mdmap}
#                }
#   * mem_dump - Linux TPMI debugfs file named "mem_dump" (e.g.,
#                /sys/kernel/debug/tpmi-0000:00:03.1/tpmi-id-00/mem_dump). Contains TPMI memory
#                dumps for all instances in text format. To read a TPMI register, parse 'mem_dump'
#                to determine the correct file position.
#   * mdmap - mem_dump map. Cache file positions for TPMI register reads to avoid reparsing
#             'mem_dump'. mdmap is a two-level dictionary: first indexed by instance number, then by
#             TPMI memory offset. The value is the file position in 'mem_dump'. Use mdmap to quickly
#             locate the file position for a given instance and register offset.
#   * position - Refers to a file position relative to the start of the file (e.g., in 'mem_dump').
#                See the standard Unix 'fsetpos()' for details.

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import stat
import typing
import contextlib
from pathlib import Path
import yaml
from pepclibs.helperlibs import Logging, YAML, ClassHelpers, FSHelpers, ProjectFiles, Trivial, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorPermissionDenied

if typing.TYPE_CHECKING:
    from typing import Final, TypedDict, Sequence, Iterable, NoReturn, Literal, cast, Generator
    from pepclibs.CPUInfoTypes import CPUInfoTypedDict
    from pepclibs.helperlibs.ProcessManager import ProcessManagerType

    class BFDictTypedDict(TypedDict, total=False):
        """
        A typed dictionary describing a register field in a TPMI specification file.

        Attributes:
            desc: A short description of the register field.
            readonly: Whether the field is read-only.
            bits: The bit positions that define the field within the register (MSB, LSB).
            bitshift: The number of bits to right-shift the register value to align the field to
                      the least significant bit (LSB).
            bitmask: The bitmask to isolate the field value.
        """

        desc: str
        readonly: bool
        bits: tuple[int, int]
        bitshift: int
        bitmask: int

    class RegDictTypedDict(TypedDict, total=False):
        """
        The typed dictionary for the register dictionary (regdict) describing a single register
        within fdict.

        Attributes:
            offset: Offset of the register within the specification.
            width: Width of the register in bits.
            readonly: Whether the register is read-only.
            fields: The bit field dictionaries (bfdicts), describing the bit-fields within the
                    register.
        """

        offset: int
        width: int
        readonly: bool
        fields: dict[str, BFDictTypedDict]

    class SDictTypedDict(TypedDict, total=False):
        """
        A typed dictionary describing a TPMI spec file. Contains only basic attributes extracted
        during directory scanning, avoiding the overhead of loading complete spec files (the "S"
        prefix indicates "scanned").

        Attributes:
            fname: Name of the TPMI feature described by the spec file.
            desc: Description of the TPMI feature.
            feature_id: TPMI ID of the feature.
            path: Path to the spec file.
        """

        name: str
        desc: str
        feature_id: int
        path: Path

    # Type for the mdmap dictionary: first indexed by instance number, then by TPMI memory offset.
    # The value is the file position in 'mem_dump'.
    _MDMapType = dict[int, dict[int, int]]

    class _AddrMDMapTypedDict(TypedDict, total=False):
        """
        A typed dictionary for used in fmap, mapping a PCI address to TPMI device information.

        Attributes:
            package: The package number associated with the TPMI device.
            mdmap: The memory dump map associated with the package.
        """

        package: int
        mdmap: _MDMapType

    _SDictKeysType = Literal["name", "desc", "feature_id"]

# Users can define this environment variable to extend the default spec files.
_SPECS_PATH_ENVVAR: Final[str] = "PEPC_TPMI_DATA_PATH"

# Maximum count of spec files per directory.
_MAX_SPEC_FILES: Final[int] = 256
# Maximum count of non-YAML files (extention is other than '.yml' or '.yaml') per directory.
_MAX_NON_YAML: Final[int] = 32
# Maximum count of spec file loading/parsing errors during scanning per spec directory.
_MAX_SCAN_LOAD_ERRORS: Final[int] = 4
# Maximum spec file size in bytes.
_MAX_SPEC_FILE_BYTES: Final[int] = 4 * 1024 * 1024 * 1024

_SDICT_KEYS: list[_SDictKeysType] = ["name", "desc", "feature_id"]

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

def _find_spec_dirs() -> list[Path]:
    """
    Find and return a list of paths to TPMI spec directories.

    Returns:
        list[Path]: A list of Path objects pointing to TPMI spec directories.
    """

    specdirs: list[Path] = []

    # Add the user-defined spec directory. This directory is optional and can be used for extending
    # the standard spec files.
    val = os.getenv(_SPECS_PATH_ENVVAR)
    if val:
        specdir = Path(val)
        idxpath = specdir / "index.yml"
        if not specdir.is_dir():
            _LOG.warning("TPMI spec files path '%s' specified in the '%s' environment "
                         "variable does not exist or it is not a directory, ignoring it",
                         specdir, _SPECS_PATH_ENVVAR)
        elif not idxpath.is_file():
            _LOG.warning("TPMI spec files path '%s' specified in the '%s' environment "
                         "variable does not contain an 'index.yml' file, ignoring it",
                         specdir, _SPECS_PATH_ENVVAR)
        else:
            specdirs.append(specdir)

    # Find the standard spec-files.
    specdir = ProjectFiles.find_project_data("pepc", "tpmi/index.yml",
                                             what="TPMI spec directory index file")
    specdirs.append(specdir.parent)
    return specdirs

def _load_sdict(specpath: Path) -> SDictTypedDict:
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
        raise Error(f"Failed to access spec file '{specpath}:\n{msg}") from err

    if st.st_size > _MAX_SPEC_FILE_BYTES:
        maxsize = Human.bytesize(_MAX_SPEC_FILE_BYTES)
        raise Error(f"Too large spec file '{specpath}', maximum allow size is {maxsize}")

    if not stat.S_ISREG(st.st_mode):
        raise Error(f"'{specpath}' is not a regular file")

    try:
        try:
            fobj = open(specpath, "r", encoding="utf-8") # pylint: disable=consider-using-with
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to open spec file '{specpath}:\n{msg}") from err

        loader = yaml.SafeLoader(fobj)
        event = None
        while True:
            event = loader.peek_event()
            if not event:
                raise Error(f"Bad spec file '{specpath}': 'feature_id' key was not found")
            if isinstance(event, yaml.ScalarEvent):
                break
            loader.get_event()

        # The first 3 keys must be: name, desc, and feature_id.
        left_keys = list(_SDICT_KEYS)
        sdict: SDictTypedDict = {}
        while len(sdict) < len(_SDICT_KEYS):
            event = loader.get_event()
            if not event:
                keys = ", ".join(left_keys)
                raise Error(f"Bad spec file '{specpath}': missing keys '{keys}'")

            key = str(event.value)

            if key not in _SDICT_KEYS:
                raise Error(f"Bad spec file '{specpath}' format: the first 3 keys must be "
                            f"'name', 'desc', and 'feature_id', got key '{key}' instead")
            if key in sdict:
                raise Error(f"Bad spec file '{specpath}': repeating key '{key}'")

            if typing.TYPE_CHECKING:
                vkey: _SDictKeysType = cast(_SDictKeysType, key)
            else:
                vkey = key
            event = loader.get_event()
            if not event:
                raise Error(f"Bad spec file '{specpath}': no value for key '{key}'")

            if vkey == "feature_id":
                sdict["feature_id"] = Trivial.str_to_int(event.value, what="'feature_id' key value")
            else:
                sdict[vkey] = str(event.value)

            left_keys.remove(vkey)
    finally:
        if fobj:
            fobj.close()

    sdict["path"] = specpath
    return sdict

class TPMI(ClassHelpers.SimpleCloseContext):
    """
    Provides methods to read and write TPMI registers, query available features, and extract
    bitfield values.

    Public Methods:
        get_known_features():
            Return information about all known TPMI features supported by the system.

        get_unknown_features():
            Return a list of TPMI feature IDs that are present but lack a specification file.

        get_sdict(fname):
            Return the spec file dictionary (sdict) for the specified TPMI feature.

        get_fdict(fname):
            Return the feature dictionary (fdict) for the specified TPMI feature.

        iter_feature(fname, packages=(), addrs=(), instances=()):
            Iterate over TPMI devices and instances for a given feature.

        read_register(fname, addr, instance, regname, bfname=None):
            Read the value of a TPMI register or a specific bitfield.

        write_register(value, fname, addr, instance, regname, bfname=None):
            Write a value to a TPMI register or a specific bitfield.

        get_bitfield(regval, fname, regname, bfname):
            Extract the value of a bitfield from a register value.
    """

    def __init__(self,
                 cpu_info: CPUInfoTypedDict,
                 pman: ProcessManagerType | None = None,
                 specdirs: Sequence[Path] = ()):
        """
        Initialize a class instance.

        Args:
            cpu_info: The CPU information dictionary.
            pman: The Process manager object that defines the host to access TPMI registers on. If
                  not provided, a local process manager will be used.
            specdirs: Spec directory paths on the local host to search for spec files. If not
                      provided, directories are auto-detected.

        Notes:
            - The reason for taking 'cpu_info' instead of a 'CPUInfo' object is to avoid a circular
              dependency between the 'TPMI' and 'CPUInfo' modules.
        """

        self.specdirs = specdirs

        self._close_pman = pman is None

        # Whether the TPMI interface is read-only.
        self._readonly = False

        if pman:
            self._pman = pman
        else:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.helperlibs import LocalProcessManager

            self._pman = LocalProcessManager.LocalProcessManager()

        vendor = cpu_info["vendor"]
        if vendor != "GenuineIntel":
            raise ErrorNotSupported(f"Unsupported CPU vendor '{vendor}'{self._pman.hostmsg}\nOnly"
                                    f"Intel CPUs support TPMI")

        self._cpu_info = cpu_info.copy()

        # The features dictionary, maps feature name to the fdict (feature dictionary).
        self._fdicts: dict[str, dict[str, RegDictTypedDict]] = {}

        if not self.specdirs:
            self.specdirs = _find_spec_dirs()

        # Keep absolute paths to spec directories - in case of an error a directory path like 'tpmi'
        # may look confusing comparint to a path like '/my/path/tpmi'.
        specdirs = self.specdirs
        self.specdirs = []
        for specdir in specdirs:
            self.specdirs.append(Path(specdir).resolve().absolute())

        # The debugfs mount point.
        self._debugfs_mnt: Path
        # Whether debugfs should be unmounted on 'close()'.
        self._unmount_debugfs: bool = False
        self._debugfs_mnt, self._unmount_debugfs = FSHelpers.mount_debugfs(pman=self._pman)

        # TPMI-related sub-directories in 'self._debugfs_mnt' (one per TPMI PCI device).
        self._tpmi_pci_paths: list[Path] = []
        self._tpmi_pci_paths = self._get_debugfs_tpmi_dirs()

        # Map feature name to the sdict, which is a partially loaded spec file dictionary.
        self._sdicts: dict[str, SDictTypedDict] = {}

        # Major and minor TPMI interface versions.
        self._major_version: int = -1
        self._minor_version: int = -1

        # Scan the spec directories and build sdicts - partially loaded spec file dictionaries.
        self._build_sdicts()

        # The feature ID -> feature name dictionary (supported features only).
        self._fid2fname: dict[int, str] = {}
        for fname, sdict in self._sdicts.items():
            self._fid2fname[sdict["feature_id"]] = fname

        # Feature maps.
        self._fmaps: dict[str, dict[str, _AddrMDMapTypedDict]] = {}
        # Package number -> set of PCI addresses.
        self._pkg2addrs: dict[int, set[str]] = {}
        # Unknown feature IDs (no spec file).
        self._unknown_fids: list[int] = []

        self._build_fmaps()

    def close(self):
        """Uninitialize the class object."""

        if self._unmount_debugfs:
            with contextlib.suppress(Error):
                self._pman.run(f"unmount {self._debugfs_mnt}")

        ClassHelpers.close(self, close_attrs=("_pman",))

    def _get_debugfs_tpmi_dirs(self) -> list[Path]:
        """
        Scan the debugfs root directory for TPMI-related sub-directories.

        Returns:
            list[Path]: The found TPMI-related sub-directories.

        Raises:
            ErrorNotSupported: If no TPMI-related sub-directories are found, indicating TPMI is not
                               supported on the system.
        """

        debugfs_tpmi_dirs: list[Path] = []
        for entry in self._pman.lsdir(self._debugfs_mnt):
            if entry["name"].startswith("tpmi-"):
                debugfs_tpmi_dirs.append(entry["path"])

        if debugfs_tpmi_dirs:
            return debugfs_tpmi_dirs

        raise ErrorNotSupported(f"No TPMI-related sub-directories found in '{self._debugfs_mnt}'"
                                f"{self._pman.hostmsg}.\nTPMI does not appear to be supported"
                                f"{self._pman.hostmsg}. Here are the possible reasons:\n"
                                f"   1. Hardware does not support TPMI.\n"
                                f"   2. The kernel is old and doesn't have the TPMI driver. TPMI "
                                f" support was added in kernel version 6.6.\n"
                                f"   3. The TPMI driver is not enabled. Try to compile the kernel "
                                f"with 'CONFIG_INTEL_TPMI' enabled.")

    def _get_debugfs_feature_path(self, addr, fname) -> Path:
        """
        Get the path to the Linux debugfs directory for a specific TPMI feature.

        Args:
            addr: PCI address of the TPMI device.
            fname: Name of the TPMI feature.

        Returns:
            Path: The path to the debugfs directory representing the specified feature.
        """

        path = self._debugfs_mnt / f"tpmi-{addr}"
        fid = self._get_sdict(fname)["feature_id"]
        path = path / f"tpmi-id-{fid:02x}"

        return path

    def _build_mdmap(self, addr, fname) -> _MDMapType:
        """
        Build and return the memory dump map (mdmap) for a TPMI feature at a given PCI device
        address.

        Args:
            addr: PCI address of the TPMI device.
            fname: Name of the TPMI feature.

        Returns:
            A two-level dictionary mapping instance numbers to register offsets, and register
            offsets to file positions in the 'mem_dump' debugfs file.

        Example:
            For a TPMI feature with two instances (0 and 1) and four register offsets (0, 4, 8, 12),
            the returned mdmap may look like:

            {
                0: {0: 48, 4: 57, 8: 66, 12: 75},
                1: {0: 77, 4: 86, 8: 95, 12: 104}
            }

            To read the register at offset 8 for instance 1, seek to position 95 in the
            corresponding 'mem_dump' debugfs file.
        """

        path = self._get_debugfs_feature_path(addr, fname)
        path = path / "mem_dump"

        _LOG.debug("reading 'mem_dump' file at '%s'", path)

        mdmap: _MDMapType = {}
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
                    # Some older kernels use the latter format.
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
                        raise Error(f"Unexpected line in TPMI file '{path}:\n{line}")

                pos += len(line) + 1

        return mdmap

    def _verify_interface_version(self,
                                  fname: str,
                                  addr: str,
                                  regname: str,
                                  bfname: str,
                                  mdmap: _MDMapType,
                                  instance: int):
        """
        Verify that the TPMI interface version is supported.

        Args:
            fname: Name of the TPMI feature.
            addr: PCI address of the TPMI device.
            regname: Name of the register to read the interface version from.
            mdmap: The memory dump map (mdmap) for the feature.
            instance: The instance number to read the interface version from.
        """

        version = self._read_register(fname, addr, instance, regname, bfname=bfname, mdmap=mdmap)

        # Bits 7:5 contain major version number, bits 4:0 contain minor version number.
        major_version = (version >> 5) & 0b111
        minor_version = version & 0b11111

        # Make sure that version is the same across all instances.
        if self._major_version == -1:
            self._major_version = major_version
        elif self._major_version != major_version:
            raise Error(f"TPMI interface major version mismatch for feature '{fname}', address "
                        f"{addr}: expected {self._major_version}, got {major_version}")

        if self._minor_version == -1:
            self._minor_version = minor_version
        elif self._minor_version != minor_version:
            raise Error(f"TPMI interface minor version mismatch for feature '{fname}', address "
                        f"{addr}: expected {self._minor_version}, got {minor_version}")

        # At this point only version 0.2 is supported.
        if self._major_version != 0 or self._minor_version != 2:
            raise ErrorNotSupported(f"Unsupported TPMI interface version "
                                    f"{self._major_version}.{self._minor_version} for feature "
                                    f"'{fname}', address {addr}{self._pman.hostmsg}.\n"
                                    f"Only TPMI version 0.2 is supported.")

    def _build_fmaps(self):
        """Build fmap for all TPMI features and save them in 'self._fmap'."""

        # A dictionary mapping feature names to the list of TPMI device addresses that provide this
        # feature.
        fname2addrs: dict[str, list[str]] = {}
        # List of unknown feature IDs.
        unknown_fids: list[int] = []

        for pci_path in self._tpmi_pci_paths:
            for entry in self._pman.lsdir(pci_path):
                match = re.match(r"^tpmi-id-([0-9a-f]+)$", entry["name"])
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
            raise ErrorNotSupported(f"No TPMI features found{self._pman.hostmsg}, checked the "
                                    f"following paths:\n * {paths}")

        if "tpmi_info" not in fname2addrs:
            dirs = "\n * ".join([str(path) for path in self.specdirs])
            raise Error(f"Spec file for the 'tpmi_info' TPMI feature was not found, checked in the "
                        f"following directories:\n * {dirs}")

        fmaps: dict[str, dict[str, _AddrMDMapTypedDict]] = {"tpmi_info": {}}

        for fname, addrs in fname2addrs.items():
            if fname not in fmaps:
                fmaps[fname] = {}

            for addr in addrs:
                if addr in fmaps[fname]:
                    continue

                # The 'tpmi_info' feature is present in every TPMI device. Use it to read the
                # package number associated with 'addr'.
                if addr not in fmaps["tpmi_info"]:
                    mdmap = self._build_mdmap(addr, "tpmi_info")

                    self._verify_interface_version("tpmi_info", addr, "TPMI_INFO_HEADER",
                                                   "INTERFACE_VERSION", mdmap, 0)

                    package = self._read_register("tpmi_info", addr, 0, "TPMI_BUS_INFO",
                                                  bfname="PACKAGE_ID", mdmap=mdmap)
                    fmaps["tpmi_info"][addr] = {"package": package, "mdmap": mdmap}

                    if package not in self._pkg2addrs:
                        self._pkg2addrs[package] = set()

                    self._pkg2addrs[package].add(addr)

                if fname == "tpmi_info":
                    continue

                package = fmaps["tpmi_info"][addr]["package"]
                fmaps[fname][addr] = {"package": package, "mdmap": {}}

        self._fmaps = fmaps
        self._unknown_fids = unknown_fids

    def _check_keys(self,
                    check_keys: Iterable[str],
                    allowed_keys: set[str],
                    mandatory_keys: set[str],
                    where: str) -> str:
        """
        Validate given keys against allowed and mandatory keys.

        Args:
            check_keys: The keys to validate.
            allowed_keys: Keys that are permitted in the dictionary.
            mandatory_keys: Keys that must be present in the dictionary.
            where: Contextual information for error messages.

        Returns:
            An error message if validation fails, otherwise an empty string.
        """

        for key in check_keys:
            if key not in allowed_keys:
                keys_str = ", ".join(allowed_keys)
                return f"Unexpected key '{key}' {where}, allowed keys are: {keys_str}"

        for key in mandatory_keys:
            if key not in check_keys:
                keys_str = ", ".join(mandatory_keys)
                return f"Missing key '{key}' {where}, mandatory keys are: {keys_str}"

        return ""

    def _parse_index_file(self, specpath: Path) -> Path:
        """
        Parse the 'index.yml' file in a spec directory and return path to the spec files
        sub-directory containing spec files for the current platform.

        Args:
            specpath: Path to the spec directory to parse the index file for.

        Returns:
            Path to a sub-directory within the spec directory containing spec files for the
            current platform
        """

        def _raise_exc(msg: str) -> NoReturn:
            """
            Raise an 'Error' exception with a formatted message.

            Args:
                msg: The error message to include in the exception.
            """

            pfx = f"Bad index file '{specpath / 'index.yml'}'"
            raise Error(f"{pfx}:\n{Error(msg).indent(2)}")

        idxpath = specpath / "index.yml"
        idxdict: dict =  YAML.load(idxpath)

        keys = {"version", "vfms"}
        where = "at the top level of the index file"
        msg = self._check_keys(idxdict, keys, keys, where)
        if msg:
            _raise_exc(msg)

        version: str = idxdict["version"]
        if version != "1.0":
            _raise_exc(f"Unsupported index format version '{version}': only version '1.0' is "
                       f"supported")

        first_vfm = ""
        vfms: dict[str, dict] = idxdict["vfms"]
        for vfm, info in vfms.items():
            keys = {"subdir", "platform_name"}
            where = f"in VFM={vfm} definition"
            msg = self._check_keys(info, keys, keys, where)
            if msg:
                _raise_exc(msg)

            if vfm == self._cpu_info["vfm"]:
                return specpath / info["subdir"]

            if not first_vfm:
                first_vfm = vfm

        # No matching platform found, use the first platform.
        _LOG.notice("No matching platform for VFM %#x found in TPMI spec index file '%s', using "
                    "spec files", self._cpu_info["vfm"], idxpath, vfms[first_vfm]["platform_name"])
        return specpath / vfms[first_vfm]["subdir"]

    def _build_sdicts(self):
        """
        Scan the spec directories, partially load spec files and build the spec dictionaries. The
        goal is to get basic information about all known TPMI features supported by the system.
        """

        sdicts: dict[str, SDictTypedDict] = {}
        for specdir in self.specdirs:
            spec_files_cnt = 0
            non_yaml_cnt = 0
            load_errors_cnt = 0

            # Parse the index file and get path to the sub-directory containing spec files for the
            # current platform.
            try:
                specsubdir = self._parse_index_file(specdir)
            except Error as err:
                _LOG.warning("Failed to parse TPMI spec index file in directory '%s':\n%s",
                             specdir, err.indent(2))
                continue

            try:
                _lsdir = os.listdir(specsubdir)
            except OSError as err:
                _LOG.warning("Failed to access TPMI spec files directory '%s':\n%s", specsubdir,
                             Error(str(err)).indent(2))
                continue

            for specname in _lsdir:
                if not specname.endswith(".yml") and not specname.endswith(".yaml"):
                    non_yaml_cnt += 1
                    if non_yaml_cnt > _MAX_NON_YAML:
                        raise Error(f"Too many non-YAML files in '{specsubdir}', maximum allowed "
                                    f"count is {_MAX_NON_YAML}")
                    continue

                try:
                    specpath = specsubdir / specname
                    sdict = _load_sdict(specpath)
                except Error as err:
                    load_errors_cnt += 1
                    if load_errors_cnt > _MAX_SCAN_LOAD_ERRORS:
                        raise Error(f"Failed to load spec file '{specpath}':\n{err.indent(2)}\n"
                                    f"Reached the maximum spec file load errors count of "
                                    f"{_MAX_SCAN_LOAD_ERRORS}") from err
                    continue

                if sdict["name"] in sdicts:
                    # Spec file for this feature was already loaded.
                    _LOG.debug("Spec file for TPMI feature '%s' was already loaded from '%s', "
                               "skipping '%s'",
                               sdict["name"], sdicts[sdict["name"]]["path"], specpath)
                    continue

                spec_files_cnt += 1
                if spec_files_cnt > _MAX_SPEC_FILES:
                    raise Error(f"Too many spec files in '{specsubdir}, maximum allowed spec files "
                                f"count is {_MAX_SPEC_FILES}")

                sdicts[sdict["name"]] = sdict

        if not sdicts:
            paths = "\n * ".join([str(path) for path in self.specdirs])
            raise ErrorNotSupported(f"No TPMI spec files found, checked the following paths:\n"
                                    f" * {paths}")

        self._sdicts = sdicts

    def _load_and_format_fdict(self, fname: str, specpath: Path) -> dict[str, RegDictTypedDict]:
        """
        Load and validate a TPMI spec file, then an return the fdict.

        Args:
            fname: Name of the TPMI feature whose spec file is being loaded.
            specpath: Path to the spec file to load.

        Returns:
            The fdict corresponding to the spec file. The fdict maps register names to their
            definitions, including bit field information with added "bitshift" and "bitmask" keys.
        """

        def _raise_exc(msg: str) -> NoReturn:
            """
            Raise an 'Error' exception with a formatted message.

            Args:
                msg: The error message to include in the exception.
            """

            pfx = f"Bad TPMI feature '{fname}' spec file '{specpath}'"
            raise Error(f"{pfx}:\n{Error(msg).indent(2)}")

        spec: dict[str, dict[str, dict[str, dict[str, dict[str, str]]]]] = YAML.load(specpath)
        if "registers" not in spec:
            _raise_exc("The 'registers' top-level key was not found")

        if "feature-id" in spec:
            # pepc versions prior to 1.6.2 used "feature-id" instead of "feature_id".
            spec["feature_id"] = spec.pop("feature-id")

        # The allowed and the mandatory top-level key names.
        keys = {"name", "desc", "feature_id", "registers"}
        where = "at the top level of the spec file"
        msg = self._check_keys(spec, keys, keys, where)
        if msg:
            _raise_exc(msg)

        fdict = spec["registers"]
        for regname, regdict in fdict.items():
            if not regname.isupper():
                _raise_exc(f"Bad TPMI register name '{regname}': should include only upper case "
                           f"characters")

            # The allowed and the mandatory regdict key names.
            keys = {"offset", "width", "fields"}
            where = f"in the '{regname}' TPMI register definition"
            msg = self._check_keys(regdict, keys, keys, where)
            if msg:
                _raise_exc(msg)

            # Validate the offset.
            offset = regdict["offset"]
            if not isinstance(offset, int):
                _raise_exc(f"Bad offset '{offset}' in TPMI register '{regname}': must be an "
                           f"integer")
            if offset % 4:
                _raise_exc(f"Bad offset '{offset}' in TPMI register '{regname}': must be multiple "
                           f"of 4 bytes")

            # Validate the width.
            width = regdict["width"]
            if not isinstance(width, int):
                _raise_exc(f"Bad width '{width}' in TPMI register '{regname}': must be an "
                           f"integer")
            if width not in (32, 64):
                _raise_exc(f"Bad width '{width}' in TPMI register '{regname}': must be either 32 "
                           f"or 64")

            all_fields_rw = True
            for bfname, bfdict in regdict["fields"].items():
                if not bfname.isupper():
                    _raise_exc(f"Bad bit field name '{bfname}' for TPMI register '{regname}': "
                               f"should include only upper case characters")

                # The allowed and the mandatory bit field dictionary key names.
                keys = {"bits", "readonly", "desc"}
                where = f"in bit field '{bfname}' of the '{regname}' TPMI register definition"
                msg = self._check_keys(bfdict, keys, keys, where)
                if msg:
                    _raise_exc(msg)

                # Make sure that the description has no newline character.
                if "\n" in bfdict["desc"]:
                    _raise_exc(f"Bad description of bit field '{bfname}' of the '{regname}' TPMI "
                               f"register: includes a newline character")

                # Verify the bits and add "bitshift" and "bitmask".
                where = f"in bit field '{bfname}' of the '{regname}' TPMI register"
                bits = Trivial.split_csv_line(bfdict["bits"], sep=":")
                if len(bits) != 2:
                    bits = bfdict["bits"]
                    _raise_exc(f"Bad 'bits' key value '{bits}' {where}: should have the "
                               f"'<high-bit>:<low-bit>' format")

                if typing.TYPE_CHECKING:
                    bftypeddict = cast(BFDictTypedDict, bfdict)
                else:
                    bftypeddict = bfdict

                what = f"the '%s' value {where}"
                highbit = Trivial.str_to_int(bits[0], what=what % bits[0])
                lowbit = Trivial.str_to_int(bits[1], what=what % bits[1])

                if highbit < lowbit:
                    bits = bfdict["bits"]
                    _raise_exc(f"Bad 'bits' key value '{bits}' {where}: high bit value '{highbit}' "
                               f"is smaller than low bit value '{lowbit}'")

                if not isinstance(bftypeddict["readonly"], bool):
                    _raise_exc(f"Bad 'readonly' key value '{bftypeddict['readonly']}' {where}: "
                               f"must be a boolean")

                all_fields_rw = all_fields_rw and not bftypeddict["readonly"]

                bitmask = ((1 << (highbit + 1)) - 1) - ((1 << lowbit) - 1)
                bftypeddict["bits"] = (highbit, lowbit)
                bftypeddict["bitshift"] = lowbit
                bftypeddict["bitmask"] = bitmask

            # Treat the register as read-write if all its fields are read-write.
            if typing.TYPE_CHECKING:
                regtypeddict = cast(RegDictTypedDict, regdict)
                regtypeddict["readonly"] = not all_fields_rw
            else:
                regdict["readonly"] = not all_fields_rw

        if typing.TYPE_CHECKING:
            return cast(dict[str, RegDictTypedDict], fdict)
        return fdict

    def _get_sdict(self, fname: str) -> SDictTypedDict:
        """
        Retrieve the sdict for a specified feature name.

        Args:
            fname: The name of the feature to retrieve the sdict for.

        Returns:
            _SDictTypedDict: The sdict associated with the given feature name.
        """

        if fname not in self._sdicts:
            known = ", ".join(self._sdicts)
            raise Error(f"Unknown feature '{fname}'{self._pman.hostname}, known features are: "
                        f"{known}")

        return self._sdicts[fname]

    def _get_fdict(self, fname: str) -> dict[str, RegDictTypedDict]:
        """
        Retrieve and cache the feature dictionary (fdict) for a given feature name.

        Args:
            fname: Name of the feature to retrieve the fdict for.

        Returns:
            The feature dictionary corresponding to 'fname' (maps register names to regdicts).

        Raises:
            ErrorNotSupported: If the feature is not supported or no spec files for the feature are
                               found.
        """

        if fname in self._fdicts:
            return self._fdicts[fname]

        sdict = self._get_sdict(fname)
        self._fdicts[fname] = self._load_and_format_fdict(fname, sdict["path"])

        return self._fdicts[fname]

    def _get_regdict(self, fname: str, regname: str) -> RegDictTypedDict:
        """
        Retrieve the regdict for a specified TPMI register and feature.

        Args:
            fname: Name of the feature containing the register.
            regname: Name of the register to retrieve.

        Returns:
            _RegDictTypedDict: Dictionary containing register information.
        """

        fdict = self._get_fdict(fname)
        if regname not in fdict:
            raise Error(f"BUG: Bad register '{regname}' for feature {fname}")

        return fdict[regname]

    def _validate_instance_offset(self,
                                  fname: str,
                                  addr: str,
                                  instance: int,
                                  regname: str,
                                  offset: int,
                                  mdmap: _MDMapType):
        """
        Validate the instance number and register offset for a TPMI feature.

        Args:
            fname: Name of the TPMI feature.
            addr: TPMI device PCI address.
            instance: Instance number to validate.
            regname: Register name.
            offset: Register offset to validate.
            mdmap: Metadata map containing valid instances and offsets.
        """

        if instance not in mdmap:
            available = Trivial.rangify(mdmap)
            raise Error(f"Bad instance number '{instance}' for TPMI feature '{fname}' and "
                        f"device '{addr}', available instances: {available}")

        if offset < 0 or offset % 4 != 0 or offset not in mdmap[instance]:
            max_offset = max(mdmap[instance])
            raise Error(f"Bad offset '{offset:#x}' for register '{regname}' of TPMI feature "
                        f"'{fname}': should be a positive integer aligned to 4 and not "
                        f"exceeding '{max_offset}'")

    def _read(self,
              fname: str,
              addr: str,
              instance: int,
              regname: str,
              offset: int,
              mdmap: _MDMapType) -> int:
        """
        Read a TPMI register value from the TPMI debugfs 'mem_dump' file.

        Args:
            fname: Name of the TPMI feature.
            addr: TPMI device PCI address.
            instance: The instance number of the TPMI feature.
            regname: The name of the register to read.
            offset: The offset of the register within the feature.
            mdmap: The memory dump map (mdmap) for the TPMI feature.

        Returns:
            The integer value of the TPMI register.
        """

        self._validate_instance_offset(fname, addr, instance, regname, offset, mdmap)

        path = self._get_debugfs_feature_path(addr, fname)
        path = path / "mem_dump"

        with self._pman.open(path, "r") as fobj:
            fobj.seek(mdmap[instance][offset])
            val = fobj.read(8)

        _LOG.debug("Read TPMI register '%s' (offset '%#x'), value is %s, file: %s, file offset %d",
                   regname, offset, val, path, mdmap[instance][offset])

        what = f"value of register '{regname}' (offset '{offset:#x}') of TPMI feature '{fname}'"
        return Trivial.str_to_int(val, base=16, what=what)

    def _get_bfdict(self, fname: str, regname: str, bfname: str) -> BFDictTypedDict:
        """
        Retrieve the bit field definition for a specified TPMI register.

        Args:
            fname: Name of the TPMI feature.
            regname: Name of the TPMI register.
            bfname: Name of the TPMI register bit field.

        Returns:
            The bit field definition dictionary for the specified register and bit field.
        """

        regdict = self._get_regdict(fname, regname)
        bfdict = regdict["fields"]

        if bfname not in bfdict:
            available = ", ".join(bfdict)
            raise Error(f"Bit field '{bfname}' not found for TPMI register '{regname}', feature "
                        f"'{fname}', available bit fields: {available}")

        return bfdict[bfname]

    def _get_bitfield(self, regval: int, fname: str, regname: str, bfname: str) -> int:
        """
        Extract the value of a specific bit field from a register value.

        Args:
            regval: The value of the register to extract the bit field from.
            fname: The name of the TPMI feature.
            regname: The name of the TPMI register.
            bfname: The name of the TPMI register bit field to extract.

        Returns:
            The integer value of the extracted bit field.
        """

        bfdict = self._get_bfdict(fname, regname, bfname)
        return (regval & bfdict["bitmask"]) >> bfdict["bitshift"]

    def _set_bitfield(self, regval: int, bitval: int, fname: str, regname: str, bfname: str) -> int:
        """
        Set a TPMI register bit field to the specified value and return the updated register value.

        Args:
            regval: The current value of the register.
            bitval: The value to set in the bit field.
            fname: The name of the TPMI feature.
            regname: The name of the TPMI register.
            bfname: The name of the bit field.

        Returns:
            The new register value with the specified bit field updated.
        """

        bfdict = self._get_bfdict(fname, regname, bfname)
        regval ^= regval & bfdict["bitmask"]
        return regval | (bitval << bfdict["bitshift"])

    def _read_register(self,
                       fname: str,
                       addr: str,
                       instance: int,
                       regname: str,
                       bfname: str = "",
                       mdmap: _MDMapType | None = None) -> int:
        """
        Read a TPMI register and optionally extract a specific bit field.

        Args:
            fname: Name of the TPMI feature the register belongs to.
            addr: TPMI device address.
            instance: TPMI instance to read the register from.
            regname: Name of the TPMI register to read.
            bfname: Bit field name to extract (read the whole register by default).
            mdmap: Optional mdmap to use for register access.

        Returns:
            Integer value of the register or the specified bit field.
        """

        regdict = self._get_regdict(fname, regname)

        offset = regdict["offset"]
        width = regdict["width"]

        if not mdmap:
            _mdmap = self._get_mdmap(fname, addr)
        else:
            _mdmap = mdmap

        val = self._read(fname, addr, instance, regname, offset, _mdmap)
        if width > 32:
            val = val + (self._read(fname, addr, instance, regname, offset + 4, _mdmap) << 32)

        if bfname:
            val = self._get_bitfield(val, fname, regname, bfname)

        _LOG.debug("Value of TPMI register '%s', bit-field '%s' is 0x%x", regname, bfname, val)
        return val

    def _write_register(self,
                        value: int,
                        fname: str,
                        addr: str,
                        instance: int,
                        regname: str,
                        bfname: str = ""):
        """
        Write a value to a TPMI register or its bit field.

        Args:
            value: Value to write to the register or bit field.
            fname: Name of the TPMI feature the register belongs to.
            addr: TPMI device address.
            instance: TPMI instance to write the register to.
            regname: Name of the TPMI register to write to.
            bfname: Name of the register bit field to write to. If not specified, writes to the
                    entire register.
        """

        if self._readonly:
            raise ErrorPermissionDenied(f"TPMI is read-only{self._pman.hostmsg}")

        regdict = self._get_regdict(fname, regname)

        if bfname:
            bfdict = self._get_bfdict(fname, regname, bfname)
            if bfdict["readonly"]:
                raise ErrorPermissionDenied(f"TPMI register '{regname}' bit field '{bfname}' of "
                                            f"feature '{fname}' is read-only"
                                            f"{self._pman.hostmsg}")
        else:
            if regdict["readonly"]:
                raise ErrorPermissionDenied(f"TPMI register '{regname}' of feature '{fname}' is "
                                            f"read-only{self._pman.hostmsg}")

        offset = regdict["offset"]
        width = regdict["width"]

        # Validate the value.
        if value < 0:
            raise Error(f"Bad value '{value}' for register '{regname}': should be a positive "
                        f"{width}-bit integer")
        max_value = (1 << width) - 1
        if value > max_value:
            raise Error(f"Too large value '{value}' for a {width}-bit register '{regname}")

        mdmap = self._get_mdmap(fname, addr)

        self._validate_instance_offset(fname, addr, instance, regname, offset, mdmap)

        path = self._get_debugfs_feature_path(addr, fname)
        path = path / "mem_write"

        _LOG.debug("Writing 0x%x to '%s' register '%s', instance '%d' at offset 0x%x of TPMI "
                   "device '%s'", value, fname, regname, instance, offset, addr)

        if bfname:
            regval = self._read_register(fname, addr, instance, regname)
            value = self._set_bitfield(regval, value, fname, regname, bfname)

        with self._pman.open(path, "r+") as fobj:
            while width > 0:
                writeval = value & 0xffffffff
                data = f"{instance},{offset},{writeval:#x}"
                _LOG.debug("Writing '%s' to '%s'", data, path)

                fobj.write(data)
                fobj.seek(0)

                width -= 32
                offset += 4
                value >>= 32

    def _get_mdmap(self, fname: str, addr: str) -> _MDMapType:
        """
        Retrieve or build the 'mem_dump' file map (mdmap) for a TPMI feature.

        Args:
            fname: Name of the TPMI feature.
            addr: PCI address of the TPMI device.

        Returns:
            The mdmap corresponding to the given feature and address.
        """

        fmap = self._fmaps[fname]
        if not fmap[addr]["mdmap"]:
            fmap[addr]["mdmap"] = self._build_mdmap(addr, fname)
        return fmap[addr]["mdmap"]

    def _format_addrs(self, addrs: Sequence[str]) -> str:
        """
        Format a list of TPMI device PCI addresses as a string.

        Args:
            addrs: List of TPMI device PCI addresses.

        Returns:
            A formatted string with a bulleted list of PCI addresses.
        """

        max_addrs = 8
        if len(addrs) > max_addrs:
            # The list of addresses may potentially be long, limit it.
            addrs = list(addrs)[:max_addrs]
            addrs.append("... and more ...")
        return "\n * ".join(addrs)

    def _validate_fname(self, fname: str):
        """
        Validate that the provided feature name.

        Args:
            fname: The feature name to validate.
        """

        if fname not in self._fmaps:
            known = ", ".join(self._fmaps)
            raise Error(f"Unknown feature '{fname}'{self._pman.hostmsg}, known features "
                        f"are:\n  {known}")

    def _validate_addr(self, fname: str, addr: str = "", package: int | None = None):
        """
        Validate the PCI address of a TPMI device for a given feature.

        Args:
            fname: Name of the feature the address belongs to.
            addr: PCI address of the TPMI device to validate.
            package: Optional package number the address belongs to.
        """

        if not addr and package is None:
            raise Error("BUG: either 'addr' or 'package' must be specified")

        if not addr:
            if package not in self._pkg2addrs:
                packages = Trivial.rangify(self._pkg2addrs)
                raise Error(f"Invalid package number '{package}'{self._pman.hostmsg}, valid"
                            f"package numbers are: {packages}")
        else:
            if addr not in self._fmaps[fname]:
                addrs = self._format_addrs(list(self._fmaps[fname]))
                raise Error(f"TPMI device '{addr}' does not exist for feature '{fname}'"
                            f"{self._pman.hostmsg}, available devices are:\n * {addrs}")

            if package is not None:
                correct_pkg = self._fmaps[fname][addr]["package"]
                if package != correct_pkg:
                    raise Error(f"Invalid package number '{package}' for TPMI device '{addr}', "
                                f"correct package numbers is '{correct_pkg}'")

    def _validate_addrs(self, fname: str, addrs: Iterable[str], packages: Iterable[int] = ()):
        """
        Validate a collection of TPMI device PCI addresses.

        Args:
            fname: Name of the feature that the addresses are associated with.
            addrs: Iterable of TPMI device PCI addresses to validate.
            packages: Optional iterable of package numbers corresponding to the addresses.
        """

        _packages: Iterable[int | None] = packages
        _addrs: Iterable[str] = addrs

        if not packages:
            _packages = (None,)
        if not addrs:
            _addrs = ("",)

        for addr in _addrs:
            for package in _packages:
                if addr or package:
                    self._validate_addr(fname, addr, package=package)

    def _validate_regname(self, fname: str, regname: str, bfname: str = ""):
        """
        Validate the existence of a register name and, optionally, a bit field name within a
        feature.

        Args:
            fname: Name of the feature to check.
            regname: Name of the register to validate.
            bfname: Name of the bit field to validate within the register.
        """

        fdict = self._get_fdict(fname)
        if regname not in fdict:
            raise Error(f"Register '{regname}' does not exist for feature '{fname}'")

        regdict = fdict[regname]
        if bfname and bfname not in regdict["fields"]:
            raise Error(f"Bit field '{bfname}' does not exist in register '{regname}' of feature "
                        f"'{fname}'")

    def _validate_instance(self, fname: str, addr: str, instance: int):
        """
        Verify that the specified instance is valid for the given TPMI device.

        Args:
            fname: The name of the TPMI device.
            addr: The address of the TPMI device.
            instance: The instance number to validate.
        """

        mdmap = self._get_mdmap(fname, addr)
        if instance in mdmap:
            return

        instances = Trivial.rangify(list(mdmap))
        raise Error(f"Instance {instance} not available for the '{fname}' TPMI device '{addr}'"
                    f"{self._pman.hostmsg}, available instances are: {instances}")

    def get_known_features(self) -> list[SDictTypedDict]:
        """
        Retrieve a list of specification dictionaries for all known features.

        Return a list of sdicts - dictionaries representing a feature that is supported by the
        target host and has an available specification file.

        Note:
            The returned dictionaries should be treated as read-only and must not be modified.

        Returns:
            List of sdicts for all known features.
        """

        sdicts = []
        for fname in self._fmaps:
            # It would be safer to return deep copy of the dictionary, but for optimization
            # purposes, avoid the copying.
            sdicts.append(self._sdicts[fname])
        return sdicts

    def get_unknown_features(self) -> list[int]:
        """
        Retrieve the list of feature IDs for unknown features. Unknown features are those supported
        by the target host for which no specification file is available.

        Returns:
            Feature IDs corresponding to unknown features.
        """

        return list(self._unknown_fids)

    def get_sdict(self, fname: str) -> SDictTypedDict:
        """
        Retrieve the spec file dictionary for a specified TPMI feature.

        Args:
            fname: Name of the TPMI feature to retrieve the dictionary for.

        Returns:
            A spec file dictionary for the specified feature.

        Note:
            The returned dictionary should be treated as read-only and must not be modified. For
            performance reasons, a deep copy is not returned.
        """

        # It would be safer to return deep copy of the dictionary, but for optimization purposes,
        # avoid the copying.
        return self._get_sdict(fname)

    def get_fdict(self, fname: str) -> dict[str, RegDictTypedDict]:
        """
        Retrieve the feature dictionary for a specified TPMI feature.

        Args:
            fname: Name of the TPMI feature to retrieve the dictionary for.

        Returns:
            A dictionary mapping feature names to their corresponding register dictionaries.

        Note:
            The returned dictionary should be treated as read-only and must not be modified. For
            performance reasons, a deep copy is not returned.
        """

        # It would be safer to return deep copy of the dictionary, but for optimization purposes,
        # avoid the copying.
        return self._get_fdict(fname)

    def iter_feature(self,
                     fname: str,
                     packages: Iterable[int] = (),
                     addrs: Iterable[str] = (),
                     instances: Iterable[int] = ()) -> Generator[tuple[int, str, int], None, None]:
        """
        Iterate over a TPMI feature and yield tuples of '(addr, package, instance)'.

        This generator yields all combinations of TPMI device PCI address, package numbers, and
        instance numbers for the specified TPMI feature. It is possible to restrict the iteration to
        specific addresses, packages, or instances by providing the corresponding arguments.

        Args:
            fname: Name of the TPMI feature to iterate.
            packages: Package numbers to include.
            addrs: TPMI device PCI addresses to include.
            instances: Instance numbers to include.

        Yields:
            Tuples of '(package, addr, instance)' for each matching feature element.
        """

        self._validate_fname(fname)
        self._validate_addrs(fname, addrs, packages=packages)

        fmap = self._fmaps[fname]

        if not addrs:
            addrs = fmap
        if not packages:
            packages = self._pkg2addrs

        for addr in addrs:
            if addr not in fmap:
                continue
            for package in packages:
                if fmap[addr]["package"] != package:
                    continue

                if instances:
                    for instance in instances:
                        self._validate_instance(fname, addr, instance)
                else:
                    mdmap = self._get_mdmap(fname, addr)
                    instances = mdmap

                for instance in instances:
                    yield (package, addr, instance)

    def read_register(self,
                      fname: str,
                      addr: str,
                      instance: int,
                      regname: str,
                      bfname: str = "") -> int:
        """
        Read a TPMI register or a bit field and return its value.

        Args:
            fname: Name of the TPMI feature to read.
            addr: Optional TPM device PCI address.
            instance: TPMI instance number to read.
            regname: Name of the TPMI register to read.
            bfname: Name of the bit field to read. Read the entire register by default.

        Returns:
            The value of the TPMI register or bit field.
        """

        self._validate_fname(fname)
        self._validate_addr(fname, addr)
        self._validate_regname(fname, regname, bfname=bfname)
        self._validate_instance(fname, addr, instance)

        return self._read_register(fname, addr, instance, regname, bfname=bfname)

    def get_bitfield(self, regval: int, fname: str, regname: str, bfname: str) -> int:
        """
        Validate the TPMI feature name and return the value of the specified bit field
        from the given register value.

        Args:
            regval: The value of the TPMI register.
            fname: The name of the TPMI feature.
            regname: The name of the TPMI register.
            bfname: The name of the bit field to extract from the register.

        Returns:
            The value of the specified bit field.
        """

        self._validate_fname(fname)
        return self._get_bitfield(regval, fname, regname, bfname)

    def write_register(self,
                       value: int,
                       fname: str,
                       addr: str,
                       instance: int,
                       regname: str,
                       bfname: str = ""):
        """
        Write a value to a TPMI register or its bit field.

        Args:
            value: Value to write to the register or bit field.
            fname: Name of the TPMI feature the register belongs to.
            addr: TPMI device address.
            instance: TPMI instance to write the register to.
            regname: Name of the TPMI register to write to.
            bfname: Name of the bit field to write to. If not provided, write the entire register.
        """

        self._validate_fname(fname)
        self._validate_addr(fname, addr)
        self._validate_regname(fname, regname, bfname=bfname)
        self._validate_instance(fname, addr, instance)

        self._write_register(value, fname, addr, instance, regname, bfname=bfname)
