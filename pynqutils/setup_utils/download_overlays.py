# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import json
import os
from distutils.command.build import build as dist_build
from distutils.dir_util import copy_tree, mkpath, remove_tree
from distutils.file_util import copy_file

from setuptools.command.build_py import build_py as _build_py

from ..runtime.detect_devices import detect_devices
from ..runtime.logging import get_logger
from .deliver_notebooks import (
    OverlayNotFoundError,
    _download_file,
    _find_local_overlay_res,
    _find_remote_overlay_res,
)

ZYNQ_ARCH = "armv7l"
ZU_ARCH = "aarch64"
CPU_ARCH = os.uname().machine
CPU_ARCH_IS_SUPPORTED = CPU_ARCH in [ZYNQ_ARCH, ZU_ARCH]
CPU_ARCH_IS_x86 = "x86" in CPU_ARCH

def download_overlays(
    path: str,
    download_all: bool = False,
    fail_at_lookup: bool = False,
    fail_at_device_detection: bool = False,
    cleanup: bool = False,
):
    """Download overlays for detected devices in destination path.

    Resolve ``overlay_res.ext`` files from  ``overlay_res.ext.link``
    json files. Downloaded ``overlay_res.ext`` files are put in a
    ``overlay_res.ext.d`` directory, with the device name added to their
    filename, as ``overlay_res.device_name.ext``.
    If the detected device is only one and is an edge device, target file is
    resolved directly to ``overlay_res.ext``.
    If target ``overlay_res.ext`` already exists, resolution is skipped.

    Parameters
    ----------
        path: str
            The path to inspect for overlays installation
        download_all: bool
            Causes all overlays to be downloaded from .link files, regardless
            of the detected devices.
        fail_at_lookup: bool
            Determines whether the function should raise an exception in case
            overlay lookup fails.
        fail_at_device_detection: bool
            Determines whether the function should raise an exception in case
            no device is detected.
        cleanup: bool
            Dictates whether .link files need to be deleted after resolution.
            If `True`, all .link files are removed as last step.
    """
    logger = get_logger()
    try:
        devices = detect_devices()
    except RuntimeError as e:
        if fail_at_device_detection:
            raise e
        devices = []
    cleanup_list = []
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.endswith(".link"):
                if not download_all:
                    if not _resolve_global_overlay_res(f, root, logger, fail_at_lookup):
                        _resolve_devices_overlay_res(
                            f, root, devices, logger, fail_at_lookup
                        )
                else:  # download all overlays regardless of detected devices
                    _resolve_all_overlay_res_from_link(f, root, logger, fail_at_lookup)
                if cleanup:
                    cleanup_list.append(os.path.join(root, f))
    for f in cleanup_list:
        os.remove(f)


def _resolve_global_overlay_res(overlay_res_link, src_path, logger, fail=False):
    """Resolve resource that is global to every device (using a ``device=None``
    when calling ``_find_remote_overlay_res``). File is downloaded in
    ``src_path``.
    """
    overlay_res_filename = os.path.splitext(overlay_res_link)[0]
    overlay_res_download_dict = _find_remote_overlay_res(
        None, os.path.join(src_path, overlay_res_link)
    )
    if overlay_res_download_dict:
        overlay_res_fullpath = os.path.join(src_path, overlay_res_filename)
        try:
            logger.info(
                "Downloading file '{}'. "
                "This may take a while"
                "...".format(overlay_res_filename)
            )
            _download_file(
                overlay_res_download_dict["url"],
                overlay_res_fullpath,
                overlay_res_download_dict["md5sum"],
                overlay_res_download_dict.get("unpack", False)
            )
        except Exception as e:
            if fail:
                raise e
        finally:
            if not os.path.isfile(overlay_res_fullpath):
                err_msg = "Could not resolve file '{}'".format(overlay_res_filename)
                logger.info(err_msg)
            else:
                return True  # overlay_res_download_dict was not empty
    return False


def _resolve_devices_overlay_res(
    overlay_res_link, src_path, devices, logger, fail=False
):
    """Resolve ``overlay_res.ext`` file for every device in ``devices``.
    Files are downloaded in a ``overlay_res.ext.d`` folder in ``src_path``.
    If the device is only one and is an edge device, file is resolved directly
    to ``overlay_res.ext``.
    """
    overlay_res_filename = os.path.splitext(overlay_res_link)[0]
    if len(devices) == 0 and not CPU_ARCH_IS_x86:
        overlay_res_fullpath = os.path.join(src_path, overlay_res_filename)
        _resolve_devices_overlay_res_helper(
            devices[0],
            src_path,
            overlay_res_filename,
            overlay_res_link,
            overlay_res_fullpath,
            logger,
            fail,
        )
        return
    for device in devices:
        overlay_res_download_path = os.path.join(src_path, overlay_res_filename + ".d")
        overlay_res_filename_split = os.path.splitext(overlay_res_filename)
        overlay_res_filename_ext = "{}.{}{}".format(
            overlay_res_filename_split[0], device, overlay_res_filename_split[1]
        )
        overlay_res_fullpath = os.path.join(
            overlay_res_download_path, overlay_res_filename_ext
        )
        _resolve_devices_overlay_res_helper(
            device,
            src_path,
            overlay_res_filename,
            overlay_res_link,
            overlay_res_fullpath,
            logger,
            fail,
            overlay_res_download_path,
        )


def _resolve_all_overlay_res_from_link(overlay_res_link, src_path, logger, fail=False):
    """Resolve every entry of ``.link`` files regardless of detected devices."""
    overlay_res_filename = os.path.splitext(overlay_res_link)[0]
    with open(os.path.join(src_path, overlay_res_link)) as f:
        links = json.load(f)
    if not _resolve_global_overlay_res(overlay_res_link, src_path, logger, fail):
        for device, download_link_dict in links.items():
            if not _find_local_overlay_res(device, overlay_res_filename, src_path):
                err_msg = "Could not resolve file '{}' for " "device '{}'".format(
                    overlay_res_filename, device
                )
                overlay_res_download_path = os.path.join(
                    src_path, overlay_res_filename + ".d"
                )
                overlay_res_filename_split = os.path.splitext(overlay_res_filename)
                overlay_res_filename_ext = "{}.{}{}".format(
                    overlay_res_filename_split[0],
                    device,
                    overlay_res_filename_split[1],
                )
                mkpath(overlay_res_download_path)
                overlay_res_fullpath = os.path.join(
                    overlay_res_download_path, overlay_res_filename_ext
                )
                try:
                    logger.info(
                        "Downloading file '{}'. "
                        "This may take a while"
                        "...".format(overlay_res_filename)
                    )
                    _download_file(
                        download_link_dict["url"],
                        overlay_res_fullpath,
                        download_link_dict["md5sum"],
                        download_link_dict.get("unpack", False)
                    )
                except Exception as e:
                    if fail:
                        raise e
                finally:
                    if not os.path.isfile(overlay_res_fullpath):
                        logger.info(err_msg)
                    if len(os.listdir(overlay_res_download_path)) == 0:
                        os.rmdir(overlay_res_download_path)


def _resolve_devices_overlay_res_helper(
    device,
    src_path,
    overlay_res_filename,
    overlay_res_link,
    overlay_res_fullpath,
    logger,
    fail=False,
    overlay_res_download_path=None,
):
    """Helper function for `_resolve_devices_overlay_res`."""
    overlay_res_src_path = _find_local_overlay_res(
        device, overlay_res_filename, src_path
    )
    err_msg = "Could not resolve file '{}' for " "device '{}'".format(
        overlay_res_filename, device
    )
    if not overlay_res_src_path:
        overlay_res_download_dict = _find_remote_overlay_res(
            device, os.path.join(src_path, overlay_res_link)
        )
        if overlay_res_download_dict:
            if overlay_res_download_path:
                mkpath(overlay_res_download_path)
            try:
                logger.info(
                    "Downloading file '{}'. This may take a while"
                    "...".format(overlay_res_filename)
                )
                _download_file(
                    overlay_res_download_dict["url"],
                    overlay_res_fullpath,
                    overlay_res_download_dict["md5sum"],
                    overlay_res_download_dict.get("unpack", False)
                )
            except Exception as e:
                if fail:
                    raise e
            finally:
                if not os.path.isfile(overlay_res_fullpath):
                    logger.info(err_msg)
                if (
                    overlay_res_download_path
                    and len(os.listdir(overlay_res_download_path)) == 0
                ):
                    os.rmdir(overlay_res_download_path)
        else:
            if fail:
                raise OverlayNotFoundError(err_msg)
            logger.info(err_msg)


class du_download_overlays(dist_build):
    """Custom distutils command to download overlays using .link files."""

    description = "Download overlays using .link files"
    user_options = [
        (
            "download-all",
            "a",
            "forcibly download every overlay from .link files, "
            "overriding download based on detected devices",
        ),
        ("force-fail", "f", "Do not complete setup if overlays lookup fails."),
    ]
    boolean_options = ["download-all", "force-fail"]

    def initialize_options(self):
        self.download_all = False
        self.force_fail = False

    def finalize_options(self):
        pass

    def run(self):
        cmd = self.get_finalized_command("build_py")
        for package, _, build_dir, _ in cmd.data_files:
            if "." not in package:  # sub-packages are skipped
                download_overlays(
                    build_dir,
                    download_all=self.download_all,
                    fail_at_lookup=self.force_fail,
                )


class build_py(_build_py):
    """Overload the standard setuptools 'build_py' command to also call the
    command 'download_overlays'.
    """

    def run(self):
        super().run()
        self.run_command("download_overlays")
