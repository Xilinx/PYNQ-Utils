# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import atexit
import json
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from distutils.command.build import build as dist_build
from distutils.dir_util import copy_tree, mkpath, remove_tree
from distutils.file_util import copy_file
from typing import Dict, Union
from xml.dom.minidom import Element
from xml.etree import ElementTree

import pkg_resources


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

        # I am assuming that sysdef.xml xsa.json, and xsa.xml are always members
        with open(self.__path("xsa.json")) as f:
            """xsa.json as a dict"""
            self.__json = json.load(f)

        # TODO: this needs fixing for the platform stuff
        # self.__presynth = self.__json["platformState"] == "pre_synth"
        self.__presynth = False

        self.__sysdef = None
        if not self.__presynth:
            """the root of the sysdef.xml element tree"""
            self.__sysdef = ElementTree.parse(self.__path("sysdef.xml")).getroot()

        """ the root of  xsa.xml element tree"""
        self.__xml = ElementTree.parse(self.__path("xsa.xml")).getroot()

        if self.__presynth:
            """get the hardware handoff from the project instead"""
            bd_name = self._find_bd_name()
            proj_name = self.__json["name"]
            self.presynth_hwh = self.__path(
                f"prj/{proj_name}.gen/sources_1/bd/{bd_name}/hw_handoff/{bd_name}.hwh"
            )
            self.presynth_vitis_tcl = self.__path(
                f"prj/{proj_name}.gen/sources_1/bd/{bd_name}/hw_handoff/{bd_name}_bd.tcl"
            )

    def is_pre_synth(self) -> bool:
        """
        Returns true if this is a pre synthesis XSA
        """
        return self.__presynth

    def _find_bd_name(self) -> str:
        """
        From xsa.json examine the file list and attempt to
        determine what the block design's name is
        """
        for f in self.__json["files"]:
            if f["type"] == "TOP_BD":
                bd_filename = os.path.basename(f["name"])
                return bd_filename.split(".")[0]
        raise XsaParsingCannotFindBlockDesignName(
            "Cannot find top block design name in XSA"
        )

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
        return a tuple of paths to extracted bitstreams defined in sysdef.xml

        """
        if self.is_pre_synth():
            return None
        return self._Xsa__path([e.attrib["Name"] for e in self.__bitstreamElements()])

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

    def createNameMatchingDefaultHwh(self) -> None:
        """
        A temporary fix to rename the default bd to match the primary bitstream.
        TODO: make it so that the whole XsaParser object is passed down into the

        Assumes that we have only one bitfile, need to test this with PR projects.
        """
        if self.is_pre_synth():
            return None

        expected_hwh = os.path.splitext(self.bitstreamPaths[0])[0] + ".hwh"
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
