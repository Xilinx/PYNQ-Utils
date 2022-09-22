# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import os
from typing import List


def extend_package(path:str, data_files: List[str]) -> None:
    if os.path.isdir(path):
        data_files.extend(
            [
                os.path.join("..", root, f)
                for root, _, files in os.walk(path)
                for f in files
            ]
        )
    elif os.path.isfile(path):
        data_files.append(os.path.join("..", path))
