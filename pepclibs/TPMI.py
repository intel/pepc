# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Tero Kristo <tero.kristo@linux.intel.com>

"""
Read and write TPMI registers on Intel CPUs. TPMI stands for "Topology Aware Register and PM Capsule
Interface" - a memory-mapped interface for accessing power management features on Intel CPUs.

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
    * feature_id - A unique integer identifier for a feature.
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
                       directory, and sub-directories containing spec files for specific
                       platforms.
    * sdict - Spec file dictionary containing basic TPMI spec file information: feature name, ID,
              description, and spec file path. Sdicts are built by partially reading spec files
              during initial scanning.
    * sdd - The spec directory dictionary. Describes a scanned and parsed spec directory, including
            the index dictionary (idxdict), and the used VFM entry (vfm).
    * instance - Logical "areas" or "components" within TPMI features, represented by integer
                 instance numbers. Specify the instance when reading or writing TPMI registers.
    * cluster - An instance of UFS (Uncore Frequency Scaling) TPMI is further divided into multiple
                clusters, each representing a copy of UFS registers. Clusters are identified by
                cluster IDs (0-7). Each cluster has its own offset within the TPMI instance memory
                space.
    * offset - TPMI register offset relative to the start of the TPMI instance memory space, as
               defined in spec files.
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
#   * cmap - Clusters map. Map UFS clusters IDs to their offsets relative to the start of the TPMI
#            instance memory space.

from __future__ import annotations # Remove when switching to Python 3.10+.

import os
import re
import stat
import typing
import contextlib
from pathlib import Path
import yaml
from pepclibs import CPUModels
from pepclibs.helperlibs import Logging, YAML, ClassHelpers, FSHelpers, ProjectFiles, Trivial, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs.Exceptions import ErrorPermissionDenied
from pepclibs.TPMIVars import DEFAULT_VFM, DEFAULT_PLATFORM_NAME, UFS_HEADER_REGNAMES

if typing.TYPE_CHECKING:
    from typing import Final, TypedDict, Sequence, Iterable, NoReturn, Literal, cast, Generator
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
            fields: The bit field dictionaries (bfdicts) describing the bit fields within the
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
            name: Name of the TPMI feature described by the spec file.
            desc: Description of the TPMI feature.
            feature_id: TPMI ID of the feature.
            path: Path to the spec file.
        """

        name: str
        desc: str
        feature_id: int
        path: Path

    # Type for the mdmap dictionary: {instance: {offset: file_position}}.
    # First indexed by instance number, then by TPMI memory offset. The value is the file position
    # in 'mem_dump'.
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

    class IdxDictVFMEntryTypedDict(TypedDict, total=False):
        """
        A typed dictionary for a VFM entry in the index dictionary (idxdict) parsed from the
        'index.yml' file in a spec directory.

        Attributes:
            subdir: The sub-directory name containing spec files for the platform.
            platform_name: The human-readable platform name.
        """

        subdir: str
        platform_name: str

    class IdxDictTypedDict(TypedDict, total=False):
        """
        A typed dictionary for the index dictionary (idxdict) parsed from the 'index.yml' file in
        a spec directory.

        Attributes:
            version: The index file format version.
            vfms: The VFM entries in the index file.
        """

        version: str
        vfms: dict[int, IdxDictVFMEntryTypedDict]

    class SDDTypedDict(TypedDict, total=False):
        """
        A typed dictionary for a scanned spec directory (sdd).

        Attributes:
            vfm: The used VFM entry from the index file (key in 'idxdict["vfms"]).
            idxdict: The index dictionary parsed from the 'index.yml' file.
        """

        vfm: int
        idxpath: Path
        idxdict: IdxDictTypedDict

# Size of the UFS header in bytes.
_UFS_HEADER_SIZE: Final[int] = 16

# Users can define this environment variable to extend the default spec files.
_SPECS_PATH_ENVVAR: Final[str] = "PEPC_TPMI_DATA_PATH"

# Maximum count of spec files per directory.
_MAX_SPEC_FILES: Final[int] = 256
# Maximum count of non-YAML files (extension is other than '.yml' or '.yaml') per directory.
_MAX_NON_YAML: Final[int] = 32
# Maximum count of spec file loading/parsing errors during scanning per spec directory.
_MAX_SCAN_LOAD_ERRORS: Final[int] = 4
# Maximum spec file size in bytes.
_MAX_SPEC_FILE_BYTES: Final[int] = 4 * 1024 * 1024 * 1024
# Maximum number of addresses to display in formatted address lists.
_MAX_FORMATTED_ADDRS: Final[int] = 8

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

    # Find the standard spec files.
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
        raise Error(f"Failed to access spec file '{specpath}':\n{msg}") from err

    if st.st_size > _MAX_SPEC_FILE_BYTES:
        maxsize = Human.bytesize(_MAX_SPEC_FILE_BYTES)
        raise Error(f"Too large spec file '{specpath}', maximum allowed size is {maxsize}")

    if not stat.S_ISREG(st.st_mode):
        raise Error(f"'{specpath}' is not a regular file")

    try:
        try:
            fobj = open(specpath, "r", encoding="utf-8") # pylint: disable=consider-using-with
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"Failed to open spec file '{specpath}':\n{msg}") from err

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

def _check_keys(check_keys: Iterable[str],
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

def _parse_index_file(specpath: Path, vfm: int) -> SDDTypedDict:
    """
    Parse the 'index.yml' file in a spec directory and return path to the spec files
    sub-directory containing spec files for the current platform.

    Args:
        specpath: Path to the spec directory to parse the index file for.
        vfm: The VFM value to match against the index file entries.

    Returns:
        Path to a sub-directory within the spec directory containing spec files for the current
        platform.
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

    if typing.TYPE_CHECKING:
        idxdict: IdxDictTypedDict = cast(IdxDictTypedDict, YAML.load(idxpath))
    else:
        idxdict = YAML.load(idxpath)

    sdd: SDDTypedDict = {"vfm": -1, "idxpath": idxpath, "idxdict": idxdict}

    keys = {"version", "vfms"}
    where = "at the top level of the index file"
    msg = _check_keys(idxdict, keys, keys, where)
    if msg:
        _raise_exc(msg)

    version: str = idxdict["version"]
    if version != "1.0":
        _raise_exc(f"Unsupported index format version '{version}': only version '1.0' is "
                   f"supported")

    vfms: dict[int, IdxDictVFMEntryTypedDict] = idxdict["vfms"]

    for _vfm, info in vfms.items():
        keys = {"subdir", "platform_name"}
        where = f"in VFM={_vfm} spec definition"
        msg = _check_keys(info, keys, keys, where)
        if msg:
            _raise_exc(msg)

        if _vfm == vfm:
            sdd["vfm"] = _vfm
            return sdd

    available_vfms = ", ".join(str(vfm) for vfm in vfms)
    raise ErrorNotFound(f"No matching platform for VFM {vfm} found in {idxpath}, available VFMs "
                        f"are: {available_vfms}")

def get_features(specdirs: Iterable[Path] = (),
                 vfm: int = -1) -> tuple[dict[str, SDictTypedDict], dict[Path, SDDTypedDict]]:
    """
    Retrieve a dictionary of sdicts (specification dictionaries) for all features described by
    available TPMI spec files. Also return the list of scanned spec directories. Do not
    verify whether the features are actually supported by the system, just scan the available spec
    files.

    If 'specdirs' is not provided, auto-detect spec directories.

    Args:
        specdirs: Spec directory paths on the local host to search for spec files. If not provided,
                  directories are auto-detected.
        vfm: The VFM value to match against specdir index file entries. If -1, do not match
             against VFM.

    Returns:
        A tuple containing:
            * A dictionary of spec dictionaries for all found TPMI features. Keys are feature names.
            * A dictionary of scanned spec directories. Keys are spec directory paths.

    Notes:
        1. During the scanning process, only the headers of spec files are read. The entire YAML
           file is not parsed, to avoid the overhead of loading complete spec files.
        2. Every spec directory must contain an 'index.yml' file, which is used to find the
           sub-directory containing spec files for the current platform based on 'vfm'.
    """

    if vfm == -1:
        _LOG.debug("No VFM specified, using default VFM %d (%s)",
                   DEFAULT_VFM, DEFAULT_PLATFORM_NAME)
        vfm = DEFAULT_VFM

    if not specdirs:
        specdirs = _find_spec_dirs()

    # Keep absolute paths to spec directories - in case of an error a directory path like 'tpmi'
    # may look confusing compared to a path like '/my/path/tpmi'.
    _specdirs: list[Path] = []
    for specdir in specdirs:
        _specdirs.append(Path(specdir).resolve().absolute())
    specdirs = _specdirs

    sdicts: dict[str, SDictTypedDict] = {}
    sdds: dict[Path, SDDTypedDict] = {}

    for specdir in specdirs:
        spec_files_cnt = 0
        non_yaml_cnt = 0
        load_errors_cnt = 0

        # Parse the index file and get path to the sub-directory containing spec files for the
        # current platform.
        try:
            sdd = _parse_index_file(specdir, vfm=vfm)
        except Error as err:
            _LOG.warning("Failed to parse TPMI spec index file in directory '%s':\n%s",
                         specdir, err.indent(2))
            continue

        specsubdir = specdir / sdd["idxdict"]["vfms"][sdd["vfm"]]["subdir"]

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
                # A spec file for this feature was already loaded.
                _LOG.debug("Spec file for TPMI feature '%s' was already loaded from '%s', "
                           "skipping '%s'",
                           sdict["name"], sdicts[sdict["name"]]["path"], specpath)
                continue

            spec_files_cnt += 1
            if spec_files_cnt > _MAX_SPEC_FILES:
                raise Error(f"Too many spec files in '{specsubdir}', maximum allowed number of "
                            f"spec files is {_MAX_SPEC_FILES}")

            sdicts[sdict["name"]] = sdict
            sdds[specdir] = sdd

    if not sdicts:
        paths = "\n * ".join([str(path) for path in specdirs])
        raise ErrorNotSupported(f"No TPMI spec files found, checked the following paths:\n"
                                f" * {paths}")

    return sdicts, sdds

class TPMI(ClassHelpers.SimpleCloseContext):
    """
    Provide methods to read and write TPMI registers, query available features, and extract
    bit field values.

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

        iter_ufs_feature(fname, packages=(), addrs=(), instances=(), clusters=()):
            Iterate over TPMI devices, instances, and clusters for the UFS feature.

        iter_feature_cluster(fname, packages=(), addrs=(), instances=(), clusters=()):
            Iterate over TPMI devices, instances, and clusters for a given feature.

        read_register(fname, addr, instance, regname, bfname=None):
            Read the value of a TPMI register or a specific bit field.

        read_ufs_register(addr, instance, regname, cluster, bfname=None):
            Read the value of a UFS TPMI register or a specific bit field.

        read_register_cluster(fname, addr, instance, cluster, regname, bfname=None):
            Read the value of a TPMI register or a specific bit field, specifying the cluster.

        write_register(value, fname, addr, instance, regname, bfname=None):
            Write a value to a TPMI register or a specific bit field.

        write_ufs_register(value, addr, instance, regname, cluster, bfname=None):
            Write a value to a UFS TPMI register or a specific bit field.

        write_register_cluster(value, fname, addr, instance, cluster, regname, bfname=None):
            Write a value to a TPMI register or a specific bit field, specifying the cluster.

        get_bitfield(regval, fname, regname, bfname):
            Extract the value of a bit field from a register value.
    """

    def __init__(self,
                 vfm: int = -1,
                 specdirs: Iterable[Path] = (),
                 base: Path | None = None,
                 pman: ProcessManagerType | None = None):
        """
        Initialize a class instance.

        Args:
            vfm: The VFM (Vendor, Family, Model) value of the current platform or when 'base' is
                 provided, of the platform the debugfs dump was captured from. Defaults to Granite
                 Rapids Xeon.
            specdirs: Spec directory paths on the local host to search for spec files. If not
                      provided, directories are auto-detected.
            base: Path to a copy of the TPMI debugfs contents (debugfs dump), in case of decoding
                  TPMI registers from a dump instead of the live system. If not provided, use the
                  live system defined by 'pman'.
            pman: The Process manager object that defines the host to access TPMI registers on. If
                  not provided, a local process manager will be used.

        Notes:
            1. TPMI is designed to be forward-compatible. If VFM is not provided, a default VFM
               from an early TPMI-capable platform generation is used (Granite Rapids Xeon),
               which is compatible with later generations like Sierra Forest Xeon.
            2. When 'base' is provided, all TPMI accesses are done against the debugfs dump located
               at 'base' instead of the live system defined by 'pman'.
        """

        self._close_pman = pman is None
        if pman:
            self._pman = pman
        else:
            # pylint: disable-next=import-outside-toplevel
            from pepclibs.helperlibs import LocalProcessManager

            self._pman = LocalProcessManager.LocalProcessManager()

        if vfm == -1:
            _LOG.debug("No VFM specified, using default VFM %d (%s)",
                       DEFAULT_VFM, DEFAULT_PLATFORM_NAME)
            vfm = DEFAULT_VFM

        vendor, _, _ = CPUModels.split_vfm(vfm)
        if vendor != CPUModels.VENDOR_INTEL:
            raise ErrorNotSupported(f"Unsupported CPU vendor {vendor}{self._pman.hostmsg}: "
                                    f"Only Intel CPUs support TPMI")

        self.vfm = vfm
        self.base = base

        # Whether the TPMI interface is read-only.
        self._readonly = False

        # The features dictionary, maps feature name to the fdict (feature dictionary).
        self._fdicts: dict[str, dict[str, RegDictTypedDict]] = {}

        # The debugfs mount point.
        self._debugfs_mnt: Path
        # Whether debugfs should be unmounted on 'close()'.
        self._unmount_debugfs: bool

        if not self.base:
            self._debugfs_mnt, self._unmount_debugfs = FSHelpers.mount_debugfs(pman=self._pman)
        else:
            # The base path plays the role of debugfs mount point when accessing a debugfs dump.
            self._debugfs_mnt = self.base
            self._unmount_debugfs = False

        # TPMI-related sub-directories in 'self._debugfs_mnt' (one per TPMI PCI device).
        self._tpmi_pci_paths: list[Path] = []
        self._tpmi_pci_paths = self._get_debugfs_tpmi_dirs()

        # The spec file dictionaries (sdicts) for all known features.
        self.sdicts: dict[str, SDictTypedDict] = {}
        # The scanned spec directory dictionaries (sdds) for all spec directories.
        self.sdds: dict[Path, SDDTypedDict] = {}

        # Scan the spec directories and build sdicts - partially loaded spec file dictionaries.
        self.sdicts, self.sdds = get_features(specdirs=specdirs, vfm=self.vfm)

        # The feature ID -> feature name dictionary (supported features only).
        self._fid2fname: dict[int, str] = {}
        for fname, sdict in self.sdicts.items():
            self._fid2fname[sdict["feature_id"]] = fname

        # Feature maps: {feature_name: {addr: _AddrMDMapTypedDict}}.
        self._fmaps: dict[str, dict[str, _AddrMDMapTypedDict]] = {}

        # Package number -> set of PCI addresses: {package: {addr1, addr2, ...}}.
        self._pkg2addrs: dict[int, set[str]] = {}

        # Unknown feature IDs (no spec file).
        self._unknown_fids: list[int] = []

        # A map of UFS feature addresses and instances to their clusters and offsets (cmap):
        #   {addr: {instance: {cluster: offset}}}.
        self._cmaps: dict[str, dict[int, dict[int, int]]] = {}

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

        # Verify the directory name matches the expected "tpmi-<PCI address>" format.
        # PCI address format: DDDD:BB:DD.F (domain:bus:device.function in hex).
        tpmi_dir_pattern = re.compile(r"^tpmi-[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]$")

        debugfs_tpmi_dirs: list[Path] = []
        for entry in self._pman.lsdir(self._debugfs_mnt):
            if tpmi_dir_pattern.match(entry["name"]):
                debugfs_tpmi_dirs.append(entry["path"])

        if debugfs_tpmi_dirs:
            return debugfs_tpmi_dirs

        expected_msg = ("Expected to find 'tpmi-<PCI address>' sub-directories "
                        "(e.g., 'tpmi-0000:00:03.1'), but found none.")

        if self.base:
            raise ErrorNotSupported(
                f"No TPMI-related sub-directories found in the debugfs dump at "
                f"'{self._debugfs_mnt}'.\n{expected_msg} The dump does not appear to contain "
                f"TPMI data.")

        raise ErrorNotSupported(
            f"No TPMI-related sub-directories found in '{self._debugfs_mnt}'.\n"
            f"{expected_msg} TPMI does not appear to be supported{self._pman.hostmsg}. "
            f"Possible reasons:\n"
            f"   1. Hardware does not support TPMI.\n"
            f"   2. The kernel is old and doesn't have the TPMI driver. TPMI support was added "
            f"in kernel version 6.6.\n"
            f"   3. The TPMI driver is not enabled. Try to compile the kernel with "
            f"'CONFIG_INTEL_TPMI' enabled.")

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

    def _drop_dead_instances(self,
                              fname: str,
                              addr: str,
                              mdmap: _MDMapType,
                              vals: dict[int, dict[int, int]]):
        """
        Drop dead (not implemented) instances from the memory dump map (mdmap) and verify that the
        TPMI interface version is supported.

        Args:
            fname: Name of the TPMI feature.
            addr: PCI address of the TPMI device.
            mdmap: The memory dump map (mdmap) for the feature.
            vals: Register values for all instances and offsets.
        """

        expected_major_version = -1
        expected_minor_version = -1
        version_reg_found = False

        fdict = self._get_fdict(fname)
        for regname, regdict in fdict.items():
            bfdicts: dict[str, BFDictTypedDict] = regdict.get("fields", {})
            if "INTERFACE_VERSION" not in bfdicts:
                continue

            version_reg_found = True

            for instance in list(mdmap):
                _LOG.debug("Verifying version for TPMI feature '%s', address %s, instance %d%s",
                           fname, addr, instance, self._pman.hostmsg)
                try:
                    regval = vals[instance][regdict["offset"]]
                except KeyError:
                    raise Error(f"BUG: missing register {regname} at offset {regdict['offset']:#x} "
                                f"for TPMI feature '{fname}', instance {instance}, address "
                                f"{addr}{self._pman.hostmsg}") from None

                bfdict = bfdicts["INTERFACE_VERSION"]
                version = (regval & bfdict["bitmask"]) >> bfdict["bitshift"]
                if version == 0xFF:
                    # Version 0xFF indicates that the instance of the feature is not
                    # implemented.
                    _LOG.debug("TPMI feature '%s', address %s, instance %d%s is not "
                               "implemented (version %#x): dropping it",
                                fname, addr, instance, self._pman.hostmsg, version)
                    mdmap[instance] = {}
                    continue

                # Verify version is supported and consistent across all instances.
                # Bits 7:5 contain major version number, bits 4:0 contain minor version number.
                major_version = (version >> 5) & 0b111
                minor_version = version & 0b11111

                # TPMI interface versions up to version 0.3 are supported.
                if major_version != 0 or minor_version > 3:
                    raise ErrorNotSupported(f"Unsupported TPMI interface version "
                                            f"{major_version}.{minor_version} for feature "
                                            f"'{fname}', address {addr}{self._pman.hostmsg}: "
                                            f"Only TPMI up to version 0.3 is supported.")

                # Verify version consistency across all instances.
                if expected_major_version == -1:
                    expected_major_version = major_version
                    expected_minor_version = minor_version
                else:
                    if expected_major_version != major_version:
                        raise Error(f"TPMI interface major version mismatch for feature '{fname}', "
                                    f"address {addr}{self._pman.hostmsg}: expected "
                                    f"{expected_major_version}, got {major_version}")
                    if expected_minor_version != minor_version:
                        raise Error(f"TPMI interface minor version mismatch for feature '{fname}', "
                                    f"address {addr}{self._pman.hostmsg}: expected "
                                    f"{expected_minor_version}, got {minor_version}")

        if not version_reg_found:
            raise Error(f"TPMI interface version register not found for feature '{fname}'")

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

        _LOG.debug("Reading 'mem_dump' of feature '%s' at '%s'", fname, path)

        mdmap: _MDMapType = {}
        pos = 0

        # Values for all the instances and offsets found in the 'mem_dump' file.
        vals: dict[int, dict[int, int]] = {}

        with self._pman.open(path, "r") as fobj:
            for line in fobj:
                line = line.rstrip()
                line_pos = 0

                # Sample line to match: "TPMI Instance:1 offset:0x40005000".
                match = re.match(r"TPMI Instance:(\d+) offset:(0x[0-9a-f]+)", line)
                if match:
                    instance = Trivial.str_to_int(match.group(1), what="instance number")
                    mdmap[instance] = {}
                    vals[instance] = {}
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
                            what = f"TPMI feature {fname} register at offset {offs:#x}, " \
                                   f"instance {instance}, file '{path}'"
                            vals[instance][offs] = Trivial.str_to_int(regval, base=16, what=what)
                            mdmap[instance][offs] = pos + line_pos
                            line_pos += 9
                            offs += 4
                    else:
                        raise Error(f"Unexpected line in TPMI file '{path}':\n{line}")

                pos += len(line) + 1

        self._drop_dead_instances(fname, addr, mdmap, vals)
        return mdmap

    def get_dummy_tpmi_info(self, addr: str, addrs: set[str]) -> tuple[_MDMapType, int]:
        """
        Generate and return a dummy 'tpmi_info' mdmap and package number for a TPMI device.

        This method covers the scenario when the 'tpmi_info' feature is missing from the debugfs
        dump. Instead of failing, a dummy mdmap is created with all 'tpmi_info' instances marked as
        dead (not implemented). A reasonable package number is assigned to the TPMI device based on
        its PCI address.

        Args:
            addr: PCI address of the TPMI device.
            addrs: Set of all PCI addresses of TPMI devices found in the debugfs dump.

        Returns:
            A tuple containing:
                * A dummy 'tpmi_info' mdmap with all instances marked as dead.
                * An assigned package number for the TPMI device.
        """

        _LOG.debug("Finding a reasonable dummy package number for TPMI device %s", addr)

        # In case of GNR/SRF, there is one PCI address per package. In case of DMR, there are 2 PCI
        # addresses per package.

        if self.vfm == CPUModels.MODELS["DIAMONDRAPIDS_X"]:
            # DMR case.
            sorted_addrs = sorted(addrs)
            addr_index = sorted_addrs.index(addr)
            package = addr_index // 2
        else:
            # GNR/SRF case.
            sorted_addrs = sorted(addrs)
            package = sorted_addrs.index(addr)

        # Pretend the 'tpmi_info' has only dead instances.
        mdmap: _MDMapType = {0: {}}

        _LOG.warning("The 'tpmi_info' feature was not found in the debugfs dump")
        _LOG.notice("Using a dummy 'tpmi_info', assigning package number %d to TPMI device %s",
                     package, addr)
        return mdmap, package

    def _build_fmaps(self):
        """Build fmap for all TPMI features and save them in 'self._fmap'."""

        # A dictionary mapping feature names to the list of TPMI device addresses that provide this
        # feature.
        fname2addrs: dict[str, list[str]] = {}
        # List of unknown feature IDs.
        unknown_fids: list[int] = []
        # Addresses of all TPMI devices.
        addrs_set: set[str] = set()

        tpmi_dir_pattern = re.compile(r"^tpmi-id-([0-9a-f]+)$")
        for pci_path in self._tpmi_pci_paths:
            for entry in self._pman.lsdir(pci_path):
                match = re.match(tpmi_dir_pattern, entry["name"])
                if not match:
                    continue

                fid = int(match.group(1), 16)
                fname = self._fid2fname.get(fid)
                if not fname:
                    # Unknown feature, no spec file for it.
                    unknown_fids.append(fid)
                    continue

                fname2addrs.setdefault(fname, [])
                addr = pci_path.name[len("tpmi-"):]
                fname2addrs[fname].append(addr)
                addrs_set.add(addr)

        if not fname2addrs:
            paths = "\n * ".join([str(path) for path in self._tpmi_pci_paths])
            if self.base:
                raise ErrorNotSupported(
                    f"No TPMI features found in the debugfs dump, checked the following "
                    f"paths:\n * {paths}")

            raise ErrorNotSupported(
                f"No TPMI features found{self._pman.hostmsg}, checked the following "
                f"paths:\n * {paths}")

        if "tpmi_info" not in fname2addrs:
            # The 'tpmi_info' feature is mandatory, because it provides package information for all
            # TPMI devices. However, for for the case of decoding a debugfs dump, it is handy to
            # allow proceeding even if the 'tpmi_info' spec file is missing.
            if not self.base:
                dirs = "\n * ".join([str(path) for path in self.sdds])
                raise Error(f"Spec file for the 'tpmi_info' TPMI feature was not found, checked in "
                            f"the following directories:\n * {dirs}")

        fmaps: dict[str, dict[str, _AddrMDMapTypedDict]] = {"tpmi_info": {}}

        for fname, addrs in fname2addrs.items():
            fmaps.setdefault(fname, {})

            for addr in addrs:
                if addr in fmaps[fname]:
                    continue

                # The 'tpmi_info' feature is present in every TPMI device. Use it to read the
                # package number associated with 'addr'.
                if addr not in fmaps["tpmi_info"]:
                    if "tpmi_info" not in fname2addrs:
                        # Handle the case when 'tpmi_info' spec file is missing in the debugfs dump
                        # scenario.
                        mdmap, package = self.get_dummy_tpmi_info(addr, addrs_set)
                    else:
                        mdmap = self._build_mdmap(addr, "tpmi_info")
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
        self._unknown_fids = sorted(set(unknown_fids))

    def _load_and_format_fdict(self, fname: str, specpath: Path) -> dict[str, RegDictTypedDict]:
        """
        Load and validate a TPMI spec file, then return the fdict.

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
            # pepc versions prior to 1.6.2 used 'feature-id' (with hyphen) instead of
            # 'feature_id' (with underscore).
            spec["feature_id"] = spec.pop("feature-id")

        # The allowed and the mandatory top-level key names.
        keys = {"name", "desc", "feature_id", "registers"}
        where = "at the top level of the spec file"
        msg = _check_keys(spec, keys, keys, where)
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
            msg = _check_keys(regdict, keys, keys, where)
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
                msg = _check_keys(bfdict, keys, keys, where)
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

        if fname not in self.sdicts:
            known = ", ".join(self.sdicts)
            raise Error(f"Unknown feature '{fname}'{self._pman.hostmsg}, known features are: "
                        f"{known}")

        return self.sdicts[fname]

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
                        f"'{fname}': Should be a positive integer aligned to 4 and not "
                        f"exceeding '{max_offset}'")

    def _adjust_ufs_offset(self, addr: str, instance: int, cluster: int, offset: int) -> int:
        """
        Adjust a TPMI UFS control register offset based on the cluster number.

        Args:
            addr: TPMI device PCI address.
            instance: The instance number of the UFS feature.
            cluster: The cluster number.
            offset: The register offset to adjust.

        Returns:
            The adjusted register offset.
        """

        coffset = self._cmaps[addr][instance][cluster]

        # UFS header registers are per-instance and not part of clusters. Cluster offsets point to
        # UFS_STATUS, which follows the 16-byte header. Since spec file offsets include the header,
        # subtract 16 bytes to get the correct offset within the cluster.
        return offset + coffset - _UFS_HEADER_SIZE

    def _read(self,
              fname: str,
              addr: str,
              instance: int,
              cluster: int,
              regname: str,
              offset: int,
              mdmap: _MDMapType) -> int:
        """
        Read a TPMI register value from the TPMI debugfs 'mem_dump' file.

        Args:
            fname: Name of the TPMI feature.
            addr: TPMI device PCI address.
            instance: The instance number of the TPMI feature.
            cluster: The cluster number.
            regname: The name of the register to read.
            offset: The offset of the register within the feature.
            mdmap: The memory dump map (mdmap) for the TPMI feature.

        Returns:
            The integer value of the TPMI register.
        """

        self._validate_instance_offset(fname, addr, instance, regname, offset, mdmap)

        path = self._get_debugfs_feature_path(addr, fname)
        path = path / "mem_dump"

        if cluster > 0:
            offset = self._adjust_ufs_offset(addr, instance, cluster, offset)

        with self._pman.open(path, "r") as fobj:
            fobj.seek(mdmap[instance][offset])
            val = fobj.read(8)

        _LOG.debug("Read 0x%s: feature '%s', register '%s', offset '%#x', file: %s, file offset %d",
                   val, fname, regname, offset, path, mdmap[instance][offset])

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
        Extract the value of a bit field from a register value.

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
                       cluster: int = 0,
                       bfname: str = "",
                       mdmap: _MDMapType | None = None) -> int:
        """
        Read a TPMI register and optionally extract a specific bit field.

        Args:
            fname: Name of the TPMI feature the register belongs to.
            addr: TPMI device address.
            instance: TPMI instance to read the register from.
            regname: Name of the TPMI register to read.
            cluster: Cluster to read the register from.
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

        # TODO: Make one read operation for 64-bit registers.
        val = self._read(fname, addr, instance, cluster, regname, offset, _mdmap)
        if width > 32:
            val_high = self._read(fname, addr, instance, cluster, regname, offset + 4, _mdmap) << 32
            val += val_high

        if bfname:
            val = self._get_bitfield(val, fname, regname, bfname)
            _LOG.debug("Value of TPMI register '%s', bit field '%s' is %#x", regname, bfname, val)
        else:
            _LOG.debug("Value of TPMI register '%s' is %#x", regname, val)

        return val

    def _write_register(self,
                        value: int,
                        fname: str,
                        addr: str,
                        instance: int,
                        regname: str,
                        cluster: int = 0,
                        bfname: str = ""):
        """
        Write a value to a TPMI register or its bit field.

        Args:
            value: Value to write to the register or bit field.
            fname: Name of the TPMI feature the register belongs to.
            addr: TPMI device address.
            instance: TPMI instance to write the register to.
            regname: Name of the TPMI register to write to.
            cluster: Cluster to write the register to.
            bfname: Name of the register bit field to write to. If not specified, writes to the
                    entire register.
        """

        if self._readonly:
            raise ErrorPermissionDenied(f"TPMI is read-only{self._pman.hostmsg}")

        regdict = self._get_regdict(fname, regname)

        if bfname:
            bfdict = self._get_bfdict(fname, regname, bfname)
            if bfdict["readonly"]:
                raise ErrorPermissionDenied(f"Bit field '{bfname}' of TPMI register '{regname}' "
                                            f"in feature '{fname}' is read-only"
                                            f"{self._pman.hostmsg}")
        else:
            if regdict["readonly"]:
                raise ErrorPermissionDenied(f"TPMI register '{regname}' in feature '{fname}' is "
                                            f"read-only{self._pman.hostmsg}")

        offset = regdict["offset"]
        width = regdict["width"]

        mdmap = self._get_mdmap(fname, addr)
        self._validate_instance_offset(fname, addr, instance, regname, offset, mdmap)

        path = self._get_debugfs_feature_path(addr, fname)
        path = path / "mem_write"

        _LOG.debug("Writing %#x to '%s' register '%s', instance '%d' at offset %#x of TPMI "
                   "device '%s'", value, fname, regname, instance, offset, addr)

        if value < 0:
            raise Error(f"Bad value '{value}' for register '{regname}': should be a positive "
                        f"{width}-bit integer")

        if bfname:
            # Validate the value.
            bfdict = self._get_bfdict(fname, regname, bfname)
            bfwidth = bfdict["bits"][0] - bfdict["bits"][1] + 1
            max_value = (1 << bfwidth) - 1
            if value > max_value:
                raise Error(f"Too large value '{value}' for a {bfwidth}-bit bit field '{bfname}' "
                            f"of register '{regname}'")

            regval = self._read_register(fname, addr, instance, regname)
            value = self._set_bitfield(regval, value, fname, regname, bfname)
        else:
            # Validate the value.
            max_value = (1 << width) - 1
            if value > max_value:
                raise Error(f"Too large value '{value}' for a {width}-bit register '{regname}'")

        if cluster > 0:
            offset = self._adjust_ufs_offset(addr, instance, cluster, offset)

        with self._pman.open(path, "r+") as fobj:
            while width > 0:
                # TODO: Can 64-bit writes be done in one operation?
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

        if len(addrs) > _MAX_FORMATTED_ADDRS:
            # The list of addresses may potentially be long, limit it.
            addrs = list(addrs)[:_MAX_FORMATTED_ADDRS]
            addrs.append("... and more ...")
        return "\n * ".join(addrs)

    def _validate_fname(self, fname: str):
        """
        Validate the provided feature name.

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
            raise Error("BUG: At least one of 'addr' or 'package' must be specified")

        if not addr:
            if package not in self._pkg2addrs:
                packages = Trivial.rangify(self._pkg2addrs)
                raise Error(f"Invalid package number '{package}'{self._pman.hostmsg}, valid "
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
                                f"correct package number is '{correct_pkg}'")

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

    def _validate_cluster(self, addr: str, instance: int, cluster: int, regname: str):
        """
        Verify that the specified cluster ID is valid for the given TPMI UFS instance.

        Args:
            addr: The address of the TPMI device.
            instance: The instance number to validate.
            cluster: The cluster ID to validate.
            regname: The register name that is being accessed.
        """

        if cluster == 0:
            return

        if regname in UFS_HEADER_REGNAMES:
            raise Error(f"Register '{regname}' cannot be accessed for cluster '{cluster}' of "
                        f"UFS TPMI device '{addr}', instance '{instance}': this register is "
                        f"per-instance, not per-cluster")

        cmap = self._get_cmap(addr, instance)
        if cluster in cmap:
            return

        clusters = Trivial.rangify(list(cmap))
        raise Error(f"Cluster {cluster} not available for the UFS TPMI device '{addr}', "
                    f"instance '{instance}'{self._pman.hostmsg}, available cluster IDs are: "
                    f"{clusters}")

    def get_known_features(self) -> dict[str, SDictTypedDict]:
        """
        Retrieve a dictionary of sdicts (specification dictionaries) for all known features.

        Returns:
            Dictionary of sdicts for all known features.

        Note:
            The returned dictionaries should be treated as read-only and must not be modified.

        """

        sdicts: dict[str, SDictTypedDict] = {}
        for fname in self._fmaps:
            # It would be safer to return deep copy of the dictionary, but for optimization
            # purposes, avoid the copying.
            sdicts[fname] = self.sdicts[fname]
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
        Iterate over a TPMI feature and yield tuples of '(package, addr, instance)'.

        Yield all TPMI device PCI address, package numbers, and instance numbers for the specified
        TPMI feature. It is possible to restrict the iteration to specific addresses, packages, or
        instances by providing the corresponding arguments.

        Note, in case of UFS feature, each instance may contain multiple clusters of registers. Use
        'iter_ufs_feature()' or 'iter_feature_cluster()' to iterate over clusters. This method
        yields only instance numbers, and cluster number is assumed to be 0.

        Args:
            fname: Name of the TPMI feature to iterate.
            packages: Package numbers to include.
            addrs: TPMI device PCI addresses to include.
            instances: Instance numbers to include.

        Yields:
            Tuples of '(package, addr, instance)' for each matching TPMI instance of feature
            registers.
        """

        self._validate_fname(fname)
        self._validate_addrs(fname, addrs, packages=packages)

        fmap = self._fmaps[fname]

        if not addrs:
            addrs = sorted(fmap)
        if not packages:
            packages = sorted(self._pkg2addrs)

        for addr in addrs:
            if addr not in fmap:
                continue

            try:
                mdmap = self._get_mdmap(fname, addr)
            except ErrorNotFound as err:
                # No instances found for this feature on this device, skip it.
                _LOG.debug(err)
                continue

            for package in packages:
                if fmap[addr]["package"] != package:
                    continue

                if instances:
                    _instances: list[int] = []
                    for instance in instances:
                        # Skip non-existing and dead instances.
                        if instance not in mdmap or not mdmap[instance]:
                            continue
                        _instances.append(instance)
                else:
                    # Skip dead instances (version was 0xFF).
                    _instances = sorted(instance for instance in mdmap if mdmap[instance])

                for instance in _instances:
                    yield (package, addr, instance)

    def _get_cmap(self, addr: str, instance: int) -> dict[int, int]:
        """
        Retrieve the clusters and their offsets for the specified TPMI UFS instance.

        Args:
            addr: TPMI device PCI address.
            instance: TPMI instance number.

        Returns:
            A dictionary mapping cluster IDs to their offsets for the specified TPMI instance.
        """

        if addr not in self._cmaps:
            self._cmaps[addr] = {}
        if instance in self._cmaps[addr]:
            return self._cmaps[addr][instance]

        # Read the UFS cluster information from the TPMI registers.
        #
        # The 8-bit 'LOCAL_FABRIC_CLUSTER_ID_MASK' bit field tells which clusters exist: if a bit is
        # set to 1, the corresponding cluster exists. There can be up to 8 clusters.
        clusters_mask = self._read_register("ufs", addr, instance, "UFS_HEADER",
                                            bfname="LOCAL_FABRIC_CLUSTER_ID_MASK")

        # The 'UFS_FABRIC_CLUSTER_OFFSET' register contains the offsets of all 8 possible clusters
        # in groups of 8 bits.
        clusters_offsets = self._read_register("ufs", addr, instance, "UFS_FABRIC_CLUSTER_OFFSET")

        cmap = self._cmaps[addr][instance] = {}
        mdmap = self._get_mdmap("ufs", addr)

        _LOG.debug("Building UFS cluster map for TPMI device '%s', instance '%d': "
                   "clusters_mask=%#x, clusters_offsets=%#x",
                   addr, instance, clusters_mask, clusters_offsets)

        for cluster in range(8):
            if clusters_mask & (1 << cluster) == 0:
                continue

            offset_index = (clusters_offsets >> (cluster * 8)) & 0xFF
            # The offset of the cluster in the register is 8-byte units, not in bytes.
            offset = offset_index * 8
            cmap[cluster] = offset

            _LOG.debug("Cluster %d: offset_index=%#x, offset=%#x", cluster, offset_index, offset)

            # Validate the cluster offset.
            coffset = self._cmaps[addr][instance][cluster]
            if coffset < 0 or coffset % 4 != 0 or coffset not in mdmap[instance]:
                max_coffset = max(mdmap[instance])
                raise Error(f"Bad cluster offset '{coffset:#x}' for UFS cluster '{cluster}' at "
                            f"address '{addr}', instance '{instance}': Should be a positive "
                            f"integer aligned to 4 and not exceeding '{max_coffset}'")

        return cmap

    def iter_ufs_feature(self,
                         packages: Iterable[int] = (),
                         addrs: Iterable[str] = (),
                         instances: Iterable[int] = (),
                         clusters: Iterable[int] = ()) -> Generator[tuple[int, str, int, int],
                                                                    None, None]:
        """
        Iterate over TPMI UFS feature and yield tuples of '(package, addr, instance, cluster)'.

        Similar to 'TPMI.TPMI.iter_feature()', but with added support for UFS clusters.

        The UFS TPMI feature is unique in that each instance may contain multiple clusters of
        registers, unlike other TPMI features which have no clusters (or one can think of it as
        there is only cluster 0).

        Args:
            packages: Package numbers to include.
            addrs: TPMI device PCI addresses to include.
            instances: Instance numbers to include.
            clusters: Cluster numbers to include.

        Yields:
            Tuples of '(package, addr, instance, cluster)' for each matching TPMI UFS instance and
            cluster.
        """

        for package, addr, instance in self.iter_feature("ufs", packages=packages, addrs=addrs,
                                                         instances=instances):
            cmap = self._get_cmap(addr, instance)
            if not clusters:
                clusters_iter: Iterable[int] = cmap
            else:
                clusters_iter = clusters

            for cluster in clusters_iter:
                if cluster not in cmap:
                    continue

                yield package, addr, instance, cluster

    def iter_feature_cluster(self,
                             fname: str,
                             packages: Iterable[int] = (),
                             addrs: Iterable[str] = (),
                             instances: Iterable[int] = (),
                             clusters: Iterable[int] = ()) -> Generator[tuple[int, str, int, int],
                                                                        None, None]:
        """
        Iterate over a TPMI feature and yield tuples of '(package, addr, instance, cluster)'.

        For UFS features, each instance may contain multiple clusters of registers. Other features
        do not have clusters, or another way to think about it is that they have only cluster 0.
        Therefore, for non-UFS features, cluster number 0 is yielded for each instance.

        Args:
            fname: Name of the TPMI feature to iterate.
            packages: Package numbers to include.
            addrs: TPMI device PCI addresses to include.
            instances: Instance numbers to include.
            clusters: Cluster numbers to include.

        Yields:
            Tuples of '(package, addr, instance, cluster)' for each matching TPMI instance and
            cluster.
        """

        if fname == "ufs":
            yield from self.iter_ufs_feature(packages=packages, addrs=addrs,
                                             instances=instances, clusters=clusters)
        else:
            for cluster in clusters:
                if cluster != 0:
                    raise Error(f"Invalid cluster '{cluster}': TPMI feature '{fname}' does not "
                                f"support clusters")
            for package, addr, instance in self.iter_feature(fname, packages=packages,
                                                             addrs=addrs,
                                                             instances=instances):
                yield package, addr, instance, 0

    def read_register(self,
                      fname: str,
                      addr: str,
                      instance: int,
                      regname: str,
                      bfname: str = "") -> int:
        """
        Read a TPMI register or a bit field and return its value.

        In case of the 'ufs' feature, use 'read_ufs_register()' or 'read_register_cluster()' to read
        registers from specific clusters. This method assumes cluster number 0 for the 'ufs'
        feature.

        Args:
            fname: Name of the TPMI feature to read.
            addr: TPMI device PCI address.
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

    def read_ufs_register(self,
                          addr: str,
                          instance: int,
                          cluster: int,
                          regname: str,
                          bfname: str = "") -> int:
        """
        Read a TPMI UFS register or a bit field and return its value.

        The special handling of UFS is because unlike other TPMI features, UFS may have multiple
        clusters per instance.

        Args:
            addr: TPMI device PCI address.
            instance: TPMI instance number to read.
            cluster: Cluster number to read.
            regname: Name of the TPMI register to read.
            bfname: Name of the bit field to read. Read the entire register by default.

        Returns:
            The value of the TPMI register or bit field.
        """

        self._validate_addr("ufs", addr)
        self._validate_regname("ufs", regname, bfname=bfname)
        self._validate_instance("ufs", addr, instance)
        self._validate_cluster(addr, instance, cluster, regname)

        return self._read_register("ufs", addr, instance, regname, cluster=cluster, bfname=bfname)

    def read_register_cluster(self,
                              fname: str,
                              addr: str,
                              instance: int,
                              cluster: int,
                              regname: str,
                              bfname: str = "") -> int:
        """
        Read a TPMI register or a bit field and return its value.

        Only the 'ufs' feature has clusters. Other features do not have clusters, or another way to
        think about it is that they have only cluster 0. Therefore, for non-'ufs' features, cluster
        number must be 0.

        Args:
            fname: Name of the TPMI feature to read.
            addr: TPMI device PCI address.
            instance: TPMI instance number to read.
            cluster: TPMI cluster number to read.
            regname: Name of the TPMI register to read.
            bfname: Name of the bit field to read. Read the entire register by default.

        Returns:
            The value of the TPMI register or bit field.
        """

        if fname == "ufs":
            return self.read_ufs_register(addr, instance, cluster, regname, bfname=bfname)

        if cluster != 0:
            raise Error(f"Invalid cluster '{cluster}': TPMI feature '{fname}' does not support "
                        f"clusters other than 0")

        return self.read_register(fname, addr, instance, regname, bfname=bfname)

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

        In case of the 'ufs' feature, use 'write_ufs_register()' or 'write_register_cluster()' to
        write registers to specific clusters. This method assumes cluster number 0 for the 'ufs'
        feature.

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

    def write_ufs_register(self,
                           value: int,
                           addr: str,
                           instance: int,
                           cluster: int,
                           regname: str,
                           bfname: str = ""):
        """
        Write a value to a TPMI UFS register or its bit field.

        The special handling of UFS is because unlike other TPMI features, UFS may have multiple
        clusters per instance.

        Args:
            value: Value to write to the register or bit field.
            addr: TPMI device address.
            instance: TPMI instance to write the register to.
            cluster: Cluster number to write the register to.
            regname: Name of the TPMI register to write to.
            bfname: Name of the bit field to write to. If not provided, write the entire register.
        """

        self._validate_addr("ufs", addr)
        self._validate_regname("ufs", regname, bfname=bfname)
        self._validate_instance("ufs", addr, instance)
        self._validate_cluster(addr, instance, cluster, regname)

        self._write_register(value, "ufs", addr, instance, regname, cluster=cluster, bfname=bfname)

    def write_register_cluster(self,
                               value: int,
                               fname: str,
                               addr: str,
                               instance: int,
                               cluster: int,
                               regname: str,
                               bfname: str = ""):
        """
        Write a value to a TPMI register or its bit field.

        Only the 'ufs' feature has clusters. Other features do not have clusters, or another way to
        think about it is that they have only cluster 0. Therefore, for non-'ufs' features, cluster
        number must be 0.

        Args:
            value: Value to write to the register or bit field.
            fname: Name of the TPMI feature the register belongs to.
            addr: TPMI device address.
            instance: TPMI instance to write the register to.
            cluster: TPMI cluster number to write the register to.
            regname: Name of the TPMI register to write to.
            bfname: Name of the bit field to write to. If not provided, write the entire register.
        """

        if fname == "ufs":
            self.write_ufs_register(value, addr, instance, cluster, regname, bfname=bfname)
        else:
            if cluster != 0:
                raise Error(f"Invalid cluster '{cluster}': TPMI feature '{fname}' does not support "
                            f"clusters")
            self.write_register(value, fname, addr, instance, regname, bfname=bfname)
