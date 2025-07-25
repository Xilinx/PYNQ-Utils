# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import os

def detect_devices():
    """Return a list containing all the detected devices names."""
    if os.getenv("BOARD"):
        return [os.getenv("BOARD")]
    else:
        raise RuntimeError("No device found in the system. Is the BOARD environment variable set?")
