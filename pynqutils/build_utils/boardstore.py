# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import os
import xml
import xml.etree.ElementTree as ET
from typing import Union
from tqdm.notebook import trange, tqdm
import json

def _default_repr(obj):
    return repr(obj)


class ReprDict(dict):
    """Subclass of the built-in dict that will display using the JupyterLab
    JSON repr.

    The class is recursive in that any entries that are also dictionaries
    will be converted to ReprDict objects when returned.

    """

    def __init__(self, *args, rootname="root", expanded=False, **kwargs):
        """Dictionary constructor

        Parameters
        ----------
        rootname : str
            The value to display at the root of the tree
        expanded : bool
            Whether the view of the tree should start expanded

        """
        self._rootname = rootname
        self._expanded = expanded

        super().__init__(*args, **kwargs)

    def _repr_json_(self):
        return json.loads(json.dumps(self, default=_default_repr)), {
            "expanded": self._expanded,
            "root": self._rootname,
        }

    def __getitem__(self, key):
        obj = super().__getitem__(key)
        if type(obj) is dict:
            return ReprDict(obj, expanded=self._expanded, rootname=key)
        else:
            return obj

def find_xml(name, path)->list:
    '''
    Returns list of xml files of name in absolute path form
    this is useful if a board folder has multiple versions
    '''
    xml_paths = []
    for root, dirs, files in os.walk(path):
        if name in files:
            xml_paths.append(os.path.join(root, name))
    return xml_paths

def find_part(xml_tree)->str:
    '''
    Part name is usually contained in a part0 component
    defined in the board.xml file
    '''
    for child in xml_tree.find('components'):
        if child.attrib['name'] == 'part0':
            return child.attrib['part_name']

def file_version(xml_tree)->str:
    """
    Returns the version of the file
    """
    return xml_tree.find('file_version').text

def resolve_paths(board_dir)->dict:
    '''
    Returns a dict of absolute paths to all board.xml files
    in a board folder, indexed by version numbers
    '''
    version_dict = {}
    board_xmls = find_xml('board.xml', board_dir)
    for xml in board_xmls:
        version_dict[os.path.normpath(xml).split(os.path.sep)[-2]] = xml

    return version_dict

def resolve_version(version_dict)->Union[str,list]:
    '''
    Given a dict of versions and absolute paths to board xmls
    returns latest version and list of possible versions
    '''
    versions = list(version_dict.keys())
    versions.sort()
    latest_version = versions[-1]

    return latest_version, versions
        

class BoardStore:
    '''
    This class parses the XilinxBoardStore repository and returns a list of 
    Board objects from selected vendors and board families.

    families: ZynqUltraScale, ZynqRFSoC, Zynq7000, Versal, KriaSOM
    vendors: Xilinx, Avnet, Digilent, iWave, OpalKelly, Trenz_Electronic, TUL
    branch: 2022.1, 2021.2, 2021.1, 2020.2, etc.
    '''
    def __init__(self, repo_path, families=None, vendors="All", branch="master"):
        self.repo_path = repo_path
        
        if not os.path.exists(repo_path):
            os.system(f'git clone https://github.com/Xilinx/XilinxBoardStore -b {branch} {repo_path}')
        
        self.boards = []
        self.populate_boards(families, vendors)

        self._curr_idx = 0
        
    def get_repo(self):
        return self.repo_path
    
    def populate_boards(self, families=None, vendors="All"):
        '''
        This function sets the boards list, we can filter the boards by family
        and by vendor.

        families: ZynqUltraScale, ZynqRFSoC, Zynq7000, Versal, KriaSOM
        vendors: Avnet, Digilent, iWave, OpalKelly, Trenz_Electronic, TUL
        '''
        # We get list of all possible vendors by listing the boards directory
        # of the XilinxBoardStore repo
        all_vendors = os.listdir(os.path.join(self.repo_path,'boards'))
        
        # If vendors is not set, then boards from all vendors will be returned
        if vendors == "All":
            vendors = all_vendors
        
        # For each board in each vendor folder, pass the board dir into the Board
        # constructor. If families not set, every board in the vendor folder will
        # be included
        for vendor in vendors:
            for board in os.listdir(os.path.join(self.repo_path, 'boards', vendor)):
                board_holder = Board(os.path.join(self.repo_path, 'boards', vendor, board))
                board_family = board_holder.find_family()
                if families == None:
                    if board_holder.part_name is not None:
                        self.boards.append(board_holder)
                elif board_family in families:
                    if board_holder.part_name is not None:
                        self.boards.append(board_holder)
                else:
                    pass
                    
    def _repr_json_(self):
        r = {}
        for b in self.boards:
            r[b.name] = {}
            r[b.name]['part'] = b.part_name
            r[b.name]['file_version'] = b.file_version
            r[b.name]['xml'] = b.board_xml_path
            r[b.name]['version'] = b.current_version
        return json.loads(json.dumps(r, default=_default_repr)), {
            "root": "boards",
        }

    def __iter__(self):
        self._curr_idx = 0
        if len(self.boards)>0:
            self._progress_bar = tqdm(total=len(self.boards))
        return self

    def __next__(self):
        if self._curr_idx >= len(self.boards):
            raise StopIteration
        else:
            ret = self.boards[self._curr_idx]
            self._progress_bar.update(1)
            self._curr_idx = self._curr_idx + 1
            return ret
    

class Boards(BoardStore):
    """
    Wrapper for API for the demo
    """
    def __init__(self, families=None):
        super().__init__(repo_path="./XilinxBoardStore", families=families)

class Board:
    '''
    The Board class interacts with the board.xml and preset.xml files in the
    board folders of the XilinxBoardStore repo. 
    '''
    
    def __str__(self):
        return self.board_root.attrib['display_name']
    
    def __repr__(self):
        return self.board_root.attrib['name']
    
    def __init__(self, board_path):
        
        board_xmls = resolve_paths(board_path)
        self.current_version, self.available_versions = resolve_version(board_xmls)
        self.board_xml_path = board_xmls[self.current_version]
        
        # Parse xml tree
        self.board_tree = ET.parse(self.board_xml_path)
        self.board_root = self.board_tree.getroot()
        
        # We need to do a try catch here because some boards don't have a preset.xml
        try:
            preset_file = self.board_root.attrib['preset_file']
            self.board_preset_path = os.path.join(os.path.split(os.path.join(self.board_xml_path))[0],preset_file)
        except:
            self.board_preset_path = []
            
        self.part_name = find_part(self.board_root)
        self.file_version = file_version(self.board_root)
        self.name = self.board_root.attrib['name']
    
    def board_typestring(self)->str:
        """
        Returns a VLNV type for the board
        """
        vendor = self.board_root.attrib['vendor']
        name = self.board_root.attrib['name']
        return f"{vendor}:{name}:part0:{self.file_version}"

    def get_preset_dict(self):
        """
        Returns a dict of presets that can be combined with the 
        metadata object when rendering

        Any parameter for the PS in this dict will overwrite
        whatever is in the metadata PS configuration
        """
        presets = {}
        preset_tree = ET.parse(self.board_preset_path)
        preset_root = preset_tree.getroot()
        preset_list = set(['PSU__DDRC__CL','PSU__DDRC__BUS_WIDTH', 'PSU__CRL_APB__CPU_R5_CTRL__FREQMHZ', 'PSU__CRF_APB__ACPU_CTRL__FREQMHZ'])
        for param in preset_root.iter('user_parameter'):
            if len(param.get('name').split(".")) >= 2:
                name = param.get('name').split(".")[1]
                if name in preset_list:
                    presets[name] = param.get('value')
        return presets

            
    def find_family(self)->str:
        '''
        We use the preset.xml file to find the board family
        Possible options right now are: Zynq7000, ZynqUltraScale and Versal
        If it's not one of the listed above this method returns 'Unknown'.
        '''
        try:
            preset_tree = ET.parse(self.board_preset_path)
            preset_root = preset_tree.getroot()
        except:
            return 'Unknown'
        
        zynquplusRFSOC = [
        'xczu21dr',
        'xczu25dr',
        'xczu27dr',
        'xczu28dr',
        'xczu29dr',
        'xczu39dr',
        'xczu42dr',
        'xczu43dr',
        'xczu46dr',
        'xczu47dr',
        'xczu48dr',
        'xczu49dr',
        'xczu57dr',
        'xczu58dr',
        'xczu59dr',
        'xczu65dr',
        'xczu67dr',
        ]
        
        if any([child.attrib['preset_proc_name'] == 'zynq_ultra_ps_e_preset' for child in preset_root]):
            if self.part_name.split('-')[0] in zynquplusRFSOC:
                return 'ZynqRFSoC'
            else:
                return 'ZynqUltraScale'
        elif any([child.attrib['preset_proc_name'] == 'ps7_preset' for child in preset_root]):
            return 'Zynq7000'
        elif any([any([subchild.attrib['name'] == 'versal_cips' for subchild in child]) for child in preset_root]):
            return 'Versal'
        elif any([child.attrib['preset_proc_name'] == 'mpsoc_preset_vsom' for child in preset_root]):
            return 'KriaSOM'
        else:
            return 'Unknown'
