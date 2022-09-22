# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import os
from typing import List, Optional


class BoardNotSupported(Exception):
    pass


def get_board(compatible: Optional[List[str]]) -> str:
    """Gets the current board from the environment variables.

    If the compatible list is None then don't check the board
    type, just return the environment variable.

    Otherwise if the board is in the compatible list return the board name.
    Or raise an error that the user the board is not supported.
    """
    board_variable = os.getenv("BOARD")
    if compatible is not None:
        if board_variable not in compatible:
            raise BoardNotSupported(f"{board_variable} is not supported")

    if board_variable is not None:
        return board_variable.lower().replace("-", "")
    else:
        return ""
