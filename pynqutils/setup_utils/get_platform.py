# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import platform


class UnsupportedPlatform(Exception):
    """Exception raised when an unsupported platform is attempted to be used"""

    pass


def get_platform() -> str:
    """Get the current platform, either edge or pcie"""
    cpu = platform.processor()
    if cpu in ["armv7l", "aarch64"]:
        return "edge"
    elif cpu in ["x86_64"]:
        return "pcie"
    else:
        raise UnsupportedPlatform("Platform with cpu {cpu} is not supported.")
