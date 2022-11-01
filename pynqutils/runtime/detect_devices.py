# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import subprocess
import re

def detect_devices():
    """ Returns a list of devices """
    examine_str = str(subprocess.check_output("xbutil examine", shell=True))
    pattern = re.compile("\[[0-9]+:[0-9]+:[0-9]+\.[0-9]+]\s*:\s+([A-Za-z0-9]+)\s+")
    devices = []
    for match in pattern.finditer(examine_str):
        devices.append(match.group(1))
    return devices


