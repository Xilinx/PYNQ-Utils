# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import glob
import os
import re
import shutil
import subprocess
import warnings
from distutils.dir_util import copy_tree
from distutils.file_util import copy_file, move_file
from shutil import rmtree

from setuptools import Distribution, Extension, find_packages, setup
from setuptools.command.build_ext import build_ext


# extend the package files by directory or by file
def extend_pynq_utils_package(data_list):
    for data in data_list:
        if os.path.isdir(data):
            pynq_utils_files.extend(
                [
                    os.path.join("..", root, f)
                    for root, _, files in os.walk(data)
                    for f in files
                ]
            )
        elif os.path.isfile(data):
            pynq_utils_files.append(os.path.join("..", data))


# Get the version
ver_file = open("./pynqutils/version.txt", "r")
ver_str = ver_file.readline()

# read the contents of your README file
from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()


# Get the files
pynq_utils_files = []

extend_pynq_utils_package(
    [
        "pynqutils/",
        "pynqutils/version.txt",
    ]
)

# Required packages
required = ["setuptools>=24.2.0", "pynqmetadata>=0.0.1", "cffi", "tqdm", "numpy", "python-magic>=0.4.25"]


setup(
    name="pynqutils",
    version=ver_str,
    description="Utilities for PYNQ",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url="https://github.com/Xilinx/PYNQ-Utils",
    author="pynq",
    author_email="pynq_support@xilinx.com",
    packages=find_packages(),
    install_requires=required,
    python_requires=">=3.5.2",
    package_data={
        "pynqutils": pynq_utils_files,
    },
    zip_safe=False,
    license="BSD 3-Clause",
)
