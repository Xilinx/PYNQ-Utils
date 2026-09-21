# Copyright (C) 2022 Xilinx, Inc
# Copyright (C) 2022 - 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

import json
import os
import shutil
import tempfile
import zipfile
from typing import Dict, Optional, Union
from xml.etree import ElementTree


class XsaParsingCannotFindBlockDesignName(Exception):
    pass


class Xsa:
    """
    XSA zip archive reader class
    """

    def __init__(self, path) -> None:
        if not os.path.exists(path):
            raise RuntimeError(f"{path} does not exist")
        """ path to the XSA file"""
        self.__archive = path
        """ path to directory for extracted files """
        self.__extracted = tempfile.mkdtemp()
        with zipfile.ZipFile(self.__archive, "r") as xsa:
            """the set of members of the zip archive"""
            self.__members = set(xsa.namelist())

        # xsa.json and xsa.xml are always members; sysdef.xml is not.
        with open(self.__path("xsa.json")) as f:
            """xsa.json as a dict"""
            self.__json = json.load(f)

        # Vitis pre-synthesis XSAs carry no sysdef.xml, so the file lists it
        # provides have to be recovered from the archive instead. The
        # platformState field in xsa.json cannot be used to tell the two apart:
        # it reads "pre_synth" even for fully implemented archives.
        self.__presynth = "sysdef.xml" not in self.__members

        self.__sysdef = None
        if not self.__presynth:
            """the root of the sysdef.xml element tree"""
            self.__sysdef = ElementTree.parse(self.__path("sysdef.xml")).getroot()

        """ the root of  xsa.xml element tree"""
        self.__xml = ElementTree.parse(self.__path("xsa.xml")).getroot()

        if self.__presynth:
            """locate the hardware handoff in the archive itself"""
            self.presynth_hwh = self.__find_default_hwh()
            self.presynth_vitis_tcl = self.__find_vitis_tcl()

    def is_pre_synth(self) -> bool:
        """
        Returns true if this is a pre synthesis XSA
        """
        return self.__presynth

    def _find_bd_name(self) -> Optional[str]:
        """
        From xsa.json examine the file list and attempt to
        determine what the block design's name is. Returns None when the
        archive does not name a top block design.
        """
        for f in self.__json.get("files", []):
            if f.get("type") == "TOP_BD":
                bd_filename = os.path.basename(f["name"])
                return bd_filename.split(".")[0]
        return None

    def __root_handoffs(self) -> list:
        """
        Hardware handoff members at the top level of the archive
        """
        return sorted(n for n in self.__members if n.endswith(".hwh") and "/" not in n)

    def __find_default_hwh(self) -> str:
        """
        Path to the top block design's handoff in an archive with no sysdef.xml

        Vivado writes the handoffs to the archive root and prefixes each IP's
        file with the name of the top block design, so the top level handoff is
        the one whose name prefixes the most siblings. Where xsa.json names the
        top block design that is used directly instead.
        """
        candidates = self.__root_handoffs()
        if not candidates:
            raise XsaParsingCannotFindBlockDesignName(
                f"No hardware handoff found in {self.__archive}"
            )

        bd_name = self._find_bd_name()
        if bd_name is not None and f"{bd_name}.hwh" in candidates:
            return self.__path(f"{bd_name}.hwh")

        stems = {name: name[: -len(".hwh")] for name in candidates}

        def sibling_count(name: str) -> int:
            return sum(
                1
                for other in candidates
                if other != name and stems[other].startswith(stems[name] + "_")
            )

        top = max(candidates, key=lambda n: (sibling_count(n), -len(stems[n])))
        return self.__path(top)

    def __find_vitis_tcl(self) -> Optional[str]:
        """
        Path to the block design tcl, when the archive carries project sources
        """
        bd_name = self._find_bd_name()
        if bd_name is None:
            return None
        wanted = f"{bd_name}_bd.tcl"
        for member in self.__members:
            if member.endswith(wanted):
                return self.__path(member)
        return None

    def __path(self, members: Union[str, list]) -> Union[str, tuple]:
        """
        return OS path(s) to extracted archive member(s)
        files are extracted if not present in the  __extracted directory
        """
        if type(members) is str:
            members = [members]
            single = True
        else:
            single = False

        missing = set(members) - (self.__members & set(members))
        if missing:
            raise RuntimeError(f"{', '.join(missing)} not found in the XSA archive")

        os_paths = []
        with zipfile.ZipFile(self.__archive, "r") as xsa:
            for member in members:
                os_path = os.path.join(self.__extracted, member)
                if not os.path.exists(os_path):
                    xsa.extract(member, self.__extracted)
                os_paths.append(os_path)
            if single:
                return os_paths[0]
            else:
                return tuple(os_paths)


class XsaParser(Xsa):
    """
    XSA parsing
    """

    def __init__(self, path: str) -> None:
        super().__init__(path)

    @property
    def bitstreamPaths(self) -> tuple:
        """
        Return a tuple of paths to extracted Zynq/ZU+ bitstreams (sysdef File Type=BIT).
        """
        if self.is_pre_synth():
            return None
        return self._Xsa__path([e.attrib["Name"] for e in self.__bitstreamElements()])

    @property
    def deviceImagePaths(self) -> tuple:
        """
        Return a tuple of paths to extracted Versal PDIs (sysdef File Type=PDI).
        """
        if self.is_pre_synth():
            return None
        return self._Xsa__path([e.attrib["Name"] for e in self.__deviceImageElements()])

    @property
    def defaultHwhPaths(self) -> tuple:
        """
        return a tuple of paths to extracted HWHs with attribute
        BD_TYPE=DEFAULT_BD in sysdef.xml
        """
        if self.is_pre_synth():
            tmp_tuple = (self.presynth_hwh, "")
            return tmp_tuple
        return self._Xsa__path(
            [e.attrib["Name"] for e in self.__hwhElements("DEFAULT_BD")]
        )

    @property
    def get_vitis_tcl_path(self) -> str:
        """
        If this is a pre_synth xsa get the tcl file used for extracting the Vitis commands
        """
        if self.is_pre_synth():
            return self.presynth_vitis_tcl
        return None

    @property
    def referenceHwhPaths(self) -> tuple:
        """
        return a tuple of paths to extracted BDCs (attribute BD_TYPE=REFERENCE_BD)
        in sysdef.xml
        """
        if self.is_pre_synth():
            return None
        return self._Xsa__path(
            [e.attrib["Name"] for e in self.__hwhElements("REFERENCE_BD")]
        )

    @property
    def pynq_modifications_log(self) -> Dict[str, str]:
        """
        Returns a dict of the PYNQ based modifications that have been applied to the XSA
        """
        try:
            pynq_mod_json_file = open(self._Xsa__path("pynq.json"), "r")
            pynq_dict = json.load(pynq_mod_json_file)
            return pynq_dict
        except:
            return {}

    @property
    def mergeableMetadataObjects(self) -> tuple:
        """
        Returns the mergeable metadata object files in the design
        """
        modifications = self.pynq_modifications_log
        return self._Xsa__path([s for s in modifications.values()])

    @property
    def referenceBdcJsonPaths(self) -> None:
        """
        returns a tuple of paths to extract the JSON files that are associated with the BDC instances
        in the design
        """
        if self.is_pre_synth():
            return None

        bdc_hwhs = [
            os.path.splitext(e.attrib["Name"])[0] + "_pynq_bdc_metadata.json"
            for e in self.__hwhElements("REFERENCE_BD")
        ]
        return self._Xsa__path(bdc_hwhs)

    def _primaryProgrammableImagePath(self) -> Optional[str]:
        """
        Return the primary programmable device image path (BIT or PDI), or None.
        """
        if self.is_pre_synth():
            return None
        if self.bitstreamPaths:
            return self.bitstreamPaths[0]
        if self.deviceImagePaths:
            return self.deviceImagePaths[0]
        return None

    def createNameMatchingDefaultHwh(self) -> None:
        """
        Copy the default BD HWH so its basename matches the primary programmable
        device image (bitstream or PDI).

        PYNQ expects ``foo.hwh`` alongside ``foo.bit`` or ``foo.pdi`` when loading
        an overlay.

        Assumes a single primary image; uses the first BIT or PDI in sysdef order.
        """
        if self.is_pre_synth():
            return None

        primary = self._primaryProgrammableImagePath()
        if primary is None:
            return None

        expected_hwh = os.path.splitext(primary)[0] + ".hwh"
        if expected_hwh not in self.defaultHwhPaths:
            shutil.copyfile(self.defaultHwhPaths[0], expected_hwh)

    def load_bdc_metadata(self) -> None:
        """
        Loads the required files for the current BDC metadata parser (such as the PYNQ metadata JSON files)
        """
        self.createNameMatchingDefaultHwh()
        self.mergeableMetadataObjects
        self.referenceHwhPaths

    # ----------------------------------------------
    # Prints out an XML structure
    # ----------------------------------------------
    def print_xml_recurse(self, node):
        """recursively walks down the XML structure"""
        for c in node:
            print(c.tag, c.attrib)
            self.print_xml_recurse(c)

    def print_xml(self, root=None):
        """Prints xml structure from root,  root=None prints sysdef.xml"""
        if root is None:
            root = self._Xsa__xml
        print(root.tag)
        print(root.attrib)
        for child in root:
            self.print_xml_recurse(child)

    # ----------------------------------------------

    def print_json(self):
        """prints the xsa.json file in the XSA"""
        print(json.dumps(self._Xsa__json, indent=2))

    def __hwhElements(self, bd_type=None) -> list:
        """
        return a list of elements in sysdef representing HWH files

        Assumes all File elements with a BD_TYPE attribute are HWH files

        Parameters
        ----------
        bd_type : str
            filter the BD_TYPE attribute, None=any

        Returns
        -------
        list
            list of xml elements
        """
        if self.is_pre_synth():
            return None
        if bd_type is None:
            return self._Xsa__sysdef.findall("File[@Type='HW_HANDOFF']")
        return self._Xsa__sysdef.findall(f"File[@BD_TYPE='{bd_type}']")

    def __bitstreamElements(self) -> list:
        """
        return a list of elements in sysdef representing bitstream files

        sysdef tag=File attributes Type=BIT
        """
        if self.is_pre_synth():
            return None
        return self._Xsa__sysdef.findall("File[@Type='BIT']")

    def __deviceImageElements(self) -> list:
        """
        return a list of elements in sysdef representing Versal PDI device images

        sysdef tag=File attributes Type=PDI
        """
        if self.is_pre_synth():
            return None
        return self._Xsa__sysdef.findall("File[@Type='PDI']")
