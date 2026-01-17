#!/usr/bin/python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Parse Intel proprietary TPMI XML files, generate pepc TPMI spec files.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing
import textwrap
from pathlib import Path
import xml.etree.ElementTree as ET
from pepclibs.helperlibs import ClassHelpers, Logging, Trivial
from pepclibs.helperlibs.Exceptions import Error

if typing.TYPE_CHECKING:
    from typing import TypedDict, IO, Sequence, Final

    class _XMLFilePathsTypedDict(TypedDict, total=False):
        """
        Typed dictionary for TPMI XML files paths.

        Attributes:
            regs: The TPMI registers XML file path ("Struct_all.os.xml").
            instances: The TPMI instances XML file paths dictionary. The keys are instance names,
                       the values are paths to the corresponding XML files. For example,
                       '{TPMI0: "AddressMap_TPMI0.os.xml"}'.
        """

        regs: Path
        instances: dict[str, Path]

    class _TPMIRegisterFieldTypedDict(TypedDict, total=False):
        """
        Typed dictionary for a TPMI register field.

        Attributes:
            name: Field name.
            desc: Field description.
            lsb: Field least significant bit.
            msb: Field most significant bit.
            bits: Field bits within the register in "msb:lsb" format.
            readonly: Whether the field is read-only.
        """

        name: str
        lsb: int
        msb: int
        bits: str
        readonly: bool
        desc: str

    class _TPMIRegisterTypedDict(TypedDict, total=False):
        """
        Typed dictionary for a TPMI register.

        Attributes:
            name: Register name.
            desc: Register description.
            width: Register width in bits
            offset: Register offset within the TPMI instance.
            fields: The register fields.
        """

        name: str
        desc: str
        width: int
        offset: int
        fields: dict[str, _TPMIRegisterFieldTypedDict]

    class _TPMIFeatureTypedDict(TypedDict, total=False):
        """
        Typed dictionary for a TPMI feature.

        Attributes:
            name: Feature name.
            desc: Feature description.
            feature_id: Feature ID (same as 'TPMI_ID' in XML files).
            registers: The feature registers.
        """

        name: str
        desc: str
        feature_id: int
        registers: dict[str, _TPMIRegisterTypedDict]

    class _TPMIFeatureInfoTypedDict(TypedDict, total=False):
        """
        TPMI Features information typed dictionary.

        Attributes:
            name: Feature name.
            desc: Feature description.
            ignore: Whether to ignore this feature during processing.
        """

        name: str
        desc: str
        ignore: bool

_LOG = Logging.getLogger(f"{Logging.MAIN_LOGGER_NAME}.pepc.{__name__}")

FEATURES_INFO: Final[dict[int, _TPMIFeatureInfoTypedDict]] = {
    0x0: {
        "name": "rapl",
        "desc": "Running Average Power Limit (RAPL) reporting and control",
        "ignore": False,
    },
    0x1: {
        "name": "pem",
        "desc": "Power and Performance Excursion Monitors",
        "ignore": False,
    },
    0x2: {
        "name": "ufs",
        "desc": "Processor uncore (fabric) monitoring and control",
        "ignore": False,
    },
    0x3: {
        "name": "pmax",
        "desc": "Management of maximum power limits",
        "ignore": False,
    },
    0x4: {
        "name": "drc",
        "desc": "Dynamic Resource Controller",
        "ignore": False,
    },
    0x5: {
        "name": "sst",
        "desc": "Intel Speed Select Technology (SST) control",
        "ignore": False,
    },
    0x6: {
        "name": "misc_ctrl",
        "desc": "Misc control and status registers - root instance",
        "ignore": False,
    },
    0x7: {
        "name": "rplm",
        "desc": "Runtime PLL Lock Status Monitor",
        "ignore": False,
    },
    0x8: {
        "name": "rit",
        "desc": "Resource Isolation Technology",
        "ignore": False,
    },
    0xA: {
        "name": "fhm",
        "desc": "FIVR Health Monitor",
        "ignore": False,
    },
    0xB: {
        "name": "misc_ctrl_a",
        "desc": "Misc control and status registers - all instances",
        "ignore": False,
    },
    0xC: {
        "name": "plr",
        "desc": "Perf Limit Reason",
        "ignore": False,
    },
    0xD: {
        "name": "bmc_ctl",
        "desc": "BMC mailbox interface",
        # Cannot be accessed by the OS, BMC-only.
        "ignore": True,
    },
    0xE: {
        "name": "oob_die_ctls",
        "desc": "Out-of-band die-scoped registers",
        # Cannot be accessed by the OS.
        "ignore": True,
    },
    0xF: {
        "name": "oob_pkg_ctls",
        "desc": "Out-of-band package-scoped registers",
        # Cannot be accessed by the OS.
        "ignore": True,
    },
    0x10: {
        "name": "pfm",
        "desc": "Proactive Frequency Management",
        "ignore": False,
    },
    0x80: {
        "name": "tpmi_control",
        "desc": "TPMI Control Interface",
        "ignore": False,
    },
    0x81: {
        "name": "tpmi_info",
        "desc": "TPMI Info Registers",
        "ignore": False,
    },
    0xFD: {
        "name": "csr_all",
        "desc": "CSR on all P-units",
        # Cannot be accessed by the OS.
        "ignore": True,
    },
    0xFE: {
        "name": "csr_compute",
        "desc": "CSR on compute P-unit",
        # Cannot be accessed by the OS.
        "ignore": True,
    },
    0xFF: {
        "name": "csr_pkg_root",
        "desc": "CSR on package P-unit",
        # Cannot be accessed by the OS.
        "ignore": True,
    }
}

# Some TPMI register bit-fields are named differently depending on the data/version of the XML
# files. This table defines such bit-field renaming to ensure consistent naming in the generated
# spec files.
_BITFIELDS_RENAME_TABLE: Final[dict[str, dict[str, dict[str, str]]]] = {
    "ufs": {"UFS_CONTROL": {"EFFICIENCY_LATENCY_CTRL_RATIO": "EFFICIENCY_LATENCY_CTRL_LOW_RATIO"}},
}

class TPMIXMLConvert(ClassHelpers.SimpleCloseContext):
    """
    Parse Intel proprietary TPMI XML files, generate pepc TPMI spec files.
    """

    def __init__(self, indir: Path):
        """
        Initialize a class instance.

        Args:
            indir: Path to the input directory with TPMI XML files.
        """

        super().__init__()

        self._indir = indir

        self._xml_paths: _XMLFilePathsTypedDict = self._get_xml_file_paths()

        self._regs: dict[str, _TPMIRegisterTypedDict] = {}
        self._features: dict[str, _TPMIFeatureTypedDict] = {}

        self._all_feature_names: list[str] = [info["name"] for info in FEATURES_INFO.values()]
        self._all_feature_names_set: set[str] = set(self._all_feature_names)

    def close(self):
        """Uninitialize the class object."""

    def _get_xml_file_paths(self) -> _XMLFilePathsTypedDict:
        """
        Scan the input directory, build and return the TPMI XML files paths dictionary.

        Returns:
            A typed dictionary with TPMI XML files paths.
        """

        xml_paths: _XMLFilePathsTypedDict = {"instances": {}}

        try:
            for path in self._indir.iterdir():
                if not path.is_file() or path.suffix.lower() != ".xml":
                    continue

                if path.name == "Struct_all.os.xml":
                    xml_paths["regs"] = path
                elif path.name.startswith("AddressMap_") and path.name.endswith(".os.xml"):
                    name = path.name[len("AddressMap_"):-len(".os.xml")]
                    xml_paths["instances"][name] = path
        except OSError as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to scan the input directory '{self._indir}':\n{errmsg}") from err

        # There must be the registers XML file and at least one instance XML file.
        if "regs" not in xml_paths:
            raise Error(f"The input directory '{self._indir}' does not contain the required TPMI "
                        f"registers XML file 'Struct_all.os.xml'")
        if not xml_paths["instances"]:
            raise Error(f"The input directory '{self._indir}' does not contain any TPMI instance "
                        f"XML files (files with names starting with 'AddressMap_' and ending "
                        f"with '.os.xml')")

        xml_paths["instances"] = dict(sorted(xml_paths["instances"].items()))
        return xml_paths

    def _parse_fields(self, xmlfields: ET.Element, reg: _TPMIRegisterTypedDict):
        """
        Parse TPMI register bit-fields and populate the corresponding register typed dictionary.

        Args:
            xmlfields: The XML element containing the register bit-fields.
            reg: The TPMI register typed dictionary to populate.
        """

        regname = reg["name"]

        for xmlfield in xmlfields:
            if xmlfield.tag != "BitField":
                raise Error(f"Unexpected 4th-level XML element tag '{xmlfield.tag}' in "
                            f"TPMI register '{regname}' in XML file "
                            f"'{self._xml_paths['regs']}'")

            for attrname in ("Name", "AccessType", "BitOffset", "BitWidth"):
                if attrname not in xmlfield.attrib:
                    _LOG.debug("Missing '%s' attribute in the following XML element:\n%s",
                               attrname, ET.tostring(xmlfield, encoding='unicode'))
                    raise Error(f"Missing '{attrname}' attribute in a bit-field of TPMI register "
                                "'{regname}' in XML file '{self._xml_paths['regs']}'")

            field: _TPMIRegisterFieldTypedDict = {}
            field["name"] = name = xmlfield.attrib["Name"]
            field["lsb"] = Trivial.str_to_int(xmlfield.attrib["BitOffset"],
                                              what=f"LSB of TPMI register {regname} field '{name}'")
            width = Trivial.str_to_int(xmlfield.attrib["BitWidth"],
                                       what=f"Width of TPMI register {regname} field '{name}'")
            field["msb"] = field["lsb"] + width - 1
            field["bits"] = f"{field['msb']}:{field['lsb']}"

            field["readonly"] = xmlfield.attrib["AccessType"].lower() != "rw"

            for xmldata in xmlfield:
                if xmldata.tag == "LongDescription":
                    for desc_data in xmldata:
                        if desc_data.tag != "Text":
                            raise Error(f"Unexpected XML element tag '{desc_data.tag}' "
                                        f"in LongDescription of field '{name}' of TPMI register "
                                        f"'{regname}' in XML file '{self._xml_paths['regs']}'")
                        if desc_data.text:
                            desc = desc_data.text.strip()
                            # Remove newlines and multiple spaces/tabs.
                            desc = " ".join(desc.split())
                            if desc.endswith('.'):
                                desc = desc[:-1]
                            field["desc"] = desc
                        break

            if name in reg["fields"]:
                raise Error(f"Duplicate field '{name}' found in TPMI register '{regname}' in XML "
                            f"file '{self._xml_paths['regs']}'")

            # Ensured the fields are sorted by MSB.
            reg["fields"][name] = field

        reg["fields"] = dict(sorted(reg["fields"].items(), key=lambda item: item[1]["msb"]))

    def _parse_regs(self):
        """
        Parse the TPMI registers XML file.
        """

        try:
            tree = ET.parse(self._xml_paths["regs"])
            root = tree.getroot()
        except (TypeError, ValueError, ET.ParseError) as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to parse the TPMI registers XML file "
                        f"'{self._xml_paths['regs']}':\n{errmsg}") from err

        for xmlreg in root:
            if xmlreg.tag != "RootBase":
                raise Error(f"Unexpected 2nd-level XML element tag '{xmlreg.tag}' in XML file "
                            f"'{self._xml_paths['regs']}'")

            reg: _TPMIRegisterTypedDict = {}

            for attrname in ("Name", "BitWidth"):
                if attrname not in xmlreg.attrib:
                    _LOG.debug("Missing '%s' attribute in the following XML element:\n%s",
                               attrname, ET.tostring(xmlreg, encoding='unicode'))
                    raise Error(f"Missing '{attrname}' attribute in a 2nd-level 'RootBase' XML "
                                f"element in XML file '{self._xml_paths['regs']}'")

            reg["name"] = name = xmlreg.attrib["Name"]
            reg["width"] = width = Trivial.str_to_int(xmlreg.attrib["BitWidth"],
                                                      what=f"TPMI register '{name}' bit width")

            # Initialize offset to zero to ensure ordering. Actual offset will be determined from
            # TPMI instance XML files.
            reg["offset"] = 0

            if width % 8 != 0:
                raise Error(f"The bit width of TPMI register '{name}' is {width}, which is "
                            f"not a multiple of 8")

            if "ShortDescription" in xmlreg.attrib:
                desc = xmlreg.attrib["ShortDescription"].strip()
                # Remove newlines and multiple spaces/tabs.
                desc = " ".join(desc.split())
                if desc.endswith('.'):
                    desc = desc[:-1]
                reg["desc"] = desc

            for idx, xmlfields in enumerate(xmlreg):
                if xmlfields.tag != "BitGroup":
                    raise Error(f"Unexpected 3rd-level XML element tag '{xmlfields.tag}' in TPMI "
                                f"{name} inf XML file '{self._xml_paths['regs']}'")
                if idx != 0:
                    raise Error(f"Multiple 'BitGroup' XML elements found in TPMI register '{name}' "
                                f"in the XML file '{self._xml_paths['regs']}'")

                reg["fields"] = {}
                self._parse_fields(xmlfields, reg)

            if name in self._regs:
                raise Error(f"Duplicate TPMI register '{name}' found in the XML file "
                            f"'{self._xml_paths['regs']}'")

            self._regs[name] = reg
            _LOG.debug("Processed TPMI register '%s'", name)

    def  _get_extension_data(self,
                             xmldata: ET.Element,
                             keyname: str,
                             regname: str,
                             instpath: Path) -> int | None:
        """
        """

        if "Data" not in xmldata.attrib:
            _LOG.debug("Missing 'Data' attribute in '<Extension Key=\"%s\">' XML element "
                       "for TPMI register '%s' in TPMI instance file '%s'",
                       keyname, regname, instpath)
            return None

        if not xmldata.attrib["Data"]:
            _LOG.debug("Empty 'Data' attribute in '<Extension Key=\"%s\">' XML element "
                       "for TPMI register '%s' in TPMI instance file '%s'",
                       keyname, regname, instpath)
            return None

        what = f"{keyname} of TPMI register '{regname}' in TPMI instance file '{instpath}'"
        data = Trivial.str_to_int(xmldata.attrib["Data"], what=what)
        return data

    def _parse_instance(self,
                        instpath: Path,
                        feature_names: Sequence[str],
                        include_intelrsvd: bool = False,
                        include_nonos: bool = False):
        """
        Parse a TPMI instance XML file.

        Args:
            instpath: Path to the TPMI instance XML file.
            feature_names: TPMI feature names to include.
            include_intelrsvd: Whether to include TPMI registers marked as "IntelRsvd".
            include_nonos: Whether to include TPMI features that are not supposed to be used by the
                           OS.
        """

        feature_names_set = set(feature_names)

        try:
            tree = ET.parse(instpath)
            root = tree.getroot()
        except (TypeError, ValueError, ET.ParseError) as err:
            errmsg = Error(str(err)).indent(2)
            raise Error(f"Failed to parse the TPMI instance XML file "
                        f"'{instpath}':\n{errmsg}") from err

        for xmlbase in root:
            if xmlbase.tag != "RootBase":
                raise Error(f"Unexpected 2nd-level XML element tag '{xmlbase.tag}' in XML file "
                            f"'{instpath}'")

            for xmlreg in xmlbase:
                if xmlreg.tag != "RegisterInstance":
                    raise Error(f"Unexpected 3rd-level XML element tag '{xmlreg.tag}' in XML file "
                                f"'{instpath}'")

                for attrname in ("Name", "AddressOffset", "ValueDataType"):
                    if attrname not in xmlreg.attrib:
                        _LOG.debug("Missing '%s' attribute in the following XML element:\n%s",
                                   attrname, ET.tostring(xmlreg, encoding='unicode'))
                        raise Error(f"Missing '{attrname}' attribute in a 3rd-level "
                                    f"'RegisterInstance' XML element in XML file '{instpath}'")

                regname = xmlreg.attrib["Name"]
                regtype = xmlreg.attrib["ValueDataType"]

                if "ShortDescription" in xmlreg.attrib:
                    desc = xmlreg.attrib["ShortDescription"].strip()
                    # Remove newlines and multiple spaces/tabs.
                    desc = " ".join(desc.split())
                    if desc.endswith('.'):
                        desc = desc[:-1]
                else:
                    desc = ""


                feature_id: int = -1
                is_intel_reserved: bool = False

                for xmldata in xmlreg:
                    if xmldata.tag == "LongDescription":
                        for desc_data in xmldata:
                            if desc_data.tag != "Text":
                                raise Error(f"Unexpected XML element tag '{desc_data.tag}' "
                                            f"in 'LongDescription' of TPMI register '{regname}' in "
                                            f"TPMI instance file '{instpath}'")
                            if desc_data.text:
                                desc = desc_data.text.strip()
                                # Remove newlines and multiple spaces/tabs.
                                desc = " ".join(desc.split())
                            break

                    if xmldata.tag == "Extension":
                        if xmldata.attrib.get("Key", "") == "TPMI_ID":
                            data = self._get_extension_data(xmldata, "TPMI_ID", regname, instpath)
                            if data is None:
                                break
                            feature_id = data
                        elif xmldata.attrib.get("Key", "") == "IntelRsvd":
                            data = self._get_extension_data(xmldata, "IntelRsvd", regname, instpath)
                            if data:
                                is_intel_reserved = True
                                break

                if is_intel_reserved and not include_intelrsvd:
                    _LOG.debug("TPMI register '%s' in TPMI instance file '%s' is marked as "
                               "IntelRsvd, skipping it", regname, instpath)
                    continue

                if feature_id == -1:
                    _LOG.debug("TPMI register '%s' in TPMI instance file '%s' has no TPMI_ID",
                               regname, instpath)
                    continue

                # Skip register definition presence verification until after TPMI_ID processing.
                # Registers without a valid # TPMI_ID will be filtered out, avoiding unnecessary
                # warnings for registers that are intentionally excluded from the registers XML
                # file.
                if regtype not in self._regs:
                    if "RESERVED" not in regname and "RSVD" not in regname:
                        _LOG.warning("TPMI register '%s' referenced in TPMI instance file '%s' is "
                                     "not defined in the TPMI registers XML file '%s'",
                                     regname, instpath, self._xml_paths["regs"])
                    continue

                if feature_id not in FEATURES_INFO:
                    _LOG.warning("Unknown TPMI feature ID %#x for TPMI register '%s' in TPMI "
                                 "instance file '%s'", feature_id, regname, instpath)
                    continue

                if FEATURES_INFO[feature_id]["name"] not in feature_names_set:
                    _LOG.debug("Skipping TPMI register '%s' in TPMI instance file '%s' because its "
                               "feature '%s' is not in the include list", regname, instpath,
                               FEATURES_INFO[feature_id]["name"])
                    continue

                if FEATURES_INFO[feature_id]["ignore"] and not include_nonos:
                    _LOG.debug("Ignoring TPMI register '%s' in TPMI instance file '%s' because "
                               "its feature ID %#x is marked as ignored",
                               regname, instpath, feature_id)
                    continue

                addr = Trivial.str_to_int(xmlreg.attrib["AddressOffset"],
                                          what=f"Address of TPMI register '{regname}' in TPMI "
                                               f"instance file '{instpath}'")

                fname = FEATURES_INFO[feature_id]["name"]

                if fname not in self._features:
                    feature: _TPMIFeatureTypedDict = {}
                    feature["name"] = fname
                    feature["desc"] = FEATURES_INFO[feature_id]["desc"]
                    feature["feature_id"] = feature_id
                    feature["registers"] = {}
                    self._features[fname] = feature

                if regname not in self._features[fname]["registers"]:
                    reg = self._regs[regtype].copy()
                    if "desc" not in reg and desc:
                        reg["desc"] = desc

                    # The offset will be adjusted a bit later to become relative to the feature
                    # base.
                    reg["offset"] = addr
                    self._features[fname]["registers"][regname] = reg

                _LOG.debug("Processed TPMI register '%s' in TPMI instance file '%s'",
                           regname, instpath)

    def _parse_instances(self,
                         feature_names: Sequence[str],
                         include_intelrsvd: bool = False,
                         include_nonos: bool = False):
        """
        Parse the TPMI instances XML files.

        Args:
            feature_names: TPMI feature names to include.
            include_intelrsvd: Whether to include TPMI registers marked as "IntelRsvd".
            include_nonos: Whether to include TPMI features that are not supposed to be used by the
                           OS.
        """

        for instname, instpath in self._xml_paths["instances"].items():
            _LOG.debug("Processing TPMI instance '%s' XML file '%s'", instname, instpath)
            self._parse_instance(instpath, feature_names,
                                 include_intelrsvd=include_intelrsvd,
                                 include_nonos=include_nonos)

    def convert(self,
                feature_names: Sequence[str] = (),
                include_intelrsvd: bool = False,
                include_nonos: bool = False):
        """
        Convert TPMI registers descriptions from XML format to pepc TPMI spec files in YAML format.

        Args:
            feature_names: TPMI feature names to include. If empty, include all features.
            include_intelrsvd: Whether to include TPMI registers marked as "IntelRsvd".
            include_nonos: Whether to include TPMI features that are not supposed to be used by the
                           OS.

        Note: Think about the registers XML file as "class definitions" for registers, and instance
              XML files as "instances" of those classes with assigned addresses and names. In many
              cases register name from the registers file will match the name in the instance file,
              but in some cases they may differ.
        """

        if not feature_names:
            feature_names = self._all_feature_names
        else:
            for feature_name in feature_names:
                if feature_name not in self._all_feature_names_set:
                    raise Error(f"Unknown TPMI feature_name '{feature_name}''. Supported features "
                                f"are:\n  {', '.join(self._all_feature_names)}")

        self._parse_regs()
        self._parse_instances(feature_names, include_intelrsvd=include_intelrsvd,
                              include_nonos=include_nonos)

        # Adjust the registers offsets to become relative to the feature base.
        for feature in self._features.values():
            # Sort the registers by offset.
            feature["registers"] = dict(sorted(feature["registers"].items(),
                                               key=lambda item: item[1]["offset"]))

            # The first register defines the feature base offset.
            base_offs = 0
            for reg in feature["registers"].values():
                base_offs = reg["offset"]
                break

            for reg in feature["registers"].values():
                reg["offset"] -= base_offs

            # Verify that offsets are unique.
            offsets = set()
            for reg in feature["registers"].values():
                if reg["offset"] in offsets:
                    raise Error(f"Duplicate offset {reg['offset']:#x} found in feature "
                                f"'{feature['name']}' for register '{reg['name']}'")
                offsets.add(reg["offset"])

    def _generate_spec_file(self, fname: str, fobj: IO[str]):
        """
        Generate a pepc TPMI spec file for a given TPMI feature.

        Args:
            fname: TPMI feature name.
            fobj: The output file object.
        """

        finfo = self._features[fname]

        fobj.write(f"name: \"{finfo['name']}\"\n")
        fobj.write("desc: >-\n")
        fobj.write(f"    {finfo['desc']}\n")
        fobj.write(f"feature_id: {finfo['feature_id']:#x}\n")
        fobj.write("\nregisters:\n")

        for regname, reginfo in finfo["registers"].items():
            fobj.write(f"    {regname.upper()}:\n")
            fobj.write(f"        offset: {reginfo['offset']}\n")
            fobj.write(f"        width: {reginfo['width']}\n")
            fobj.write("        fields:\n")

            for fldname, fldinfo in reginfo["fields"].items():
                # Apply bit-field renaming if needed.
                if finfo['name'] in _BITFIELDS_RENAME_TABLE:
                    if regname in _BITFIELDS_RENAME_TABLE[finfo['name']]:
                        if fldname in _BITFIELDS_RENAME_TABLE[finfo['name']][regname]:
                            fldname = _BITFIELDS_RENAME_TABLE[finfo['name']][regname][fldname]

                fobj.write(f"            {fldname.upper()}:\n")
                fobj.write(f"                bits: \"{fldinfo['bits']}\"\n")
                fobj.write(f"                readonly: {str(fldinfo['readonly']).lower()}\n")

                if "desc" not in fldinfo:
                    continue

                fobj.write("                desc: >-\n")
                desc = textwrap.fill(fldinfo["desc"], width=100, initial_indent=" " * 20,
                                     subsequent_indent=" " * 20)
                fobj.write(f"{desc}\n")

    def generate_spec_files(self, outdir: Path):
        """
        Generate pepc TPMI spec files for all processed TPMI features.

        Args:
            outdir: Path to the output directory for the generated pepc TPMI spec files.
        """

        for finfo in self._features.values():
            outfile = outdir / f"{finfo['name']}.yml"
            _LOG.debug("Saving TPMI feature '%s' pepc TPMI spec file '%s'", finfo['name'], outfile)

            try:
                with outfile.open("w", encoding="utf-8") as fobj:
                    self._generate_spec_file(finfo['name'], fobj)
            except OSError as err:
                errmsg = Error(str(err)).indent(2)
                raise Error(f"Failed to save TPMI feature '{finfo['name']}' pepc TPMI spec file "
                            f"'{outfile}':\n{errmsg}") from err
