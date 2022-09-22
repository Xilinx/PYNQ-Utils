# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import re


# Parse version number
def find_version(file_path):
    with open(file_path, "r") as fp:
        version_file = fp.read()
        version_match = re.search(
            r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M
        )
    if version_match:
        return version_match.group(1)
    raise NameError("Version string must be defined in {}.".format(file_path))
