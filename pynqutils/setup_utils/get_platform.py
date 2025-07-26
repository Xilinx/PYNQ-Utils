# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import platform
import os

class UnsupportedPlatform(Exception):
    """Exception raised when an unsupported platform is attempted to be used"""

    pass


def get_platform() -> str:
    """Get the current platform"""
    # Detect if we are running on a PYNQ board running Classic PYNQ
    on_target = os.path.isfile('/proc/device-tree/chosen/pynq_board')

    if on_target or os.getenv("BOARD"):
        return "edge"
    else:
        raise UnsupportedPlatform("Platform with cpu {cpu} is not supported.")
