# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import json
import os
import shutil
import tempfile
from distutils.dir_util import copy_tree, mkpath, remove_tree
from distutils.file_util import copy_file

from ..runtime.logging import get_logger


def deliver_notebooks(
    device_name: str,
    src_path: str,
    dst_path: str,
    name: str,
    folder: bool = False,
    overlays_res_lookup: bool = True,
):
    """Deliver notebooks to target destination path.

    If a ``overlay_res.ext.link`` file or a ``overlay_res.ext.d`` folders is
    found, then ``overlay_res.ext`` (where ``.ext`` represents a generic file
    extension) is considered to be a file that need to be resolved dynamically,
    based on ``device_name``.
    The following resolution strategy is applied when inspecting ``src_path``:

        1. If an ``overlay_res.ext`` file is found, prioritize that file and do
           not perform any resolution.
        2. In case step 1 fails, if a ``overlay_res.ext.d`` folder is found,
           try to retrieve the right ``overlay_res.ext`` file from there. The
           files in this folder are expected to contain the device name as a
           string, before the file extension ``.ext``.
           Format should be ``overlay_res.device_name.ext``.
        3. In case step 2 fails, if there is an ``overlay_res.ext.link`` file,
           attempt to download the correct file from the provided url, assumed
           that a valid entry for ``device_name`` is available in the ``.link``
           json file.
        4. If all steps fail, notebooks that are in the same folder as
           ``overlay_res.ext`` are not delivered, and the user is warned.

    For simplicity, it is assumed that ``.link`` files and ``.d`` folders are
    located next to the notebooks that use the associated resource. Folders
    that does not contain notebooks will not be inspected.

    In case no ``.link`` or ``overlay_res.d`` files are found, notebooks are
    simply copied as is, no resolution is performed.
    It is assumed that for this scenario, overlays are delivered somewhere
    else.

    Parameters
    ----------
        device_name: str
            The target device name to use when doing resolution of ``.link``
            files and ``.d`` folders. If an ``overlay_res.ext`` file is also
            found, no resolution will be done and ``device_name`` will be
            ignored, as it is assumed that the ``overlay_res.ext`` file is
            prioritized and no automatic resolution is expected
        src_path: str
            The source path to copy from
        dst_path: str
            The destination path to copy to
        name: str
            The name of the notebooks module
        folder: bool
            Indicates whether to use ``name`` as target folder to copy
            notebooks, inside ``dst_path``. Notebooks will be copied directly
            in ``dst_path`` if ``False``.
        overlays_res_lookup: bool
            Dynamic resolution of ``.link`` files and ``.d`` folders is
            disabled if ```False``.
    """
    logger = get_logger()

    dst_fullpath = os.path.join(dst_path, name) if folder else dst_path
    files_to_copy = {}
    files_to_move = {}
    for root, dirs, files in os.walk(src_path):
        # If there is at least one notebook, inspect the folder
        if [f for f in files if f.endswith(".ipynb")]:
            # If folder is in the list of files to copy, remove it as it is
            # going to be inspected
            if root in files_to_copy:
                files_to_copy.pop(root)
            relpath = os.path.relpath(root, src_path)
            relpath = "" if relpath == "." else relpath
            try:
                files_to_copy_tmp = {}
                files_to_move_tmp = {}
                for d in dirs:
                    if d.endswith(".d"):
                        if overlays_res_lookup:
                            _resolve_overlay_res_from_folder(
                                device_name,
                                d,
                                root,
                                dst_fullpath,
                                relpath,
                                files_to_copy_tmp,
                            )
                    elif d != "__pycache__":  # exclude __pycache__ folder
                        dir_dst_path = os.path.join(dst_fullpath, relpath, d)
                        files_to_copy_tmp[os.path.join(root, d)] = dir_dst_path
                for f in files:
                    if f.endswith(".link"):
                        if overlays_res_lookup:
                            _resolve_overlay_res_from_link(
                                device_name,
                                f,
                                root,
                                dst_fullpath,
                                relpath,
                                files_to_copy_tmp,
                                files_to_move_tmp,
                                logger,
                            )
                    else:
                        file_dst_path = os.path.join(dst_fullpath, relpath, f)
                        files_to_copy_tmp[os.path.join(root, f)] = file_dst_path
                # No OverlayNotFoundError exception raised, can add
                # files_to_copy_tmp to files_to_copy
                files_to_copy.update(files_to_copy_tmp)
                # and files_to_move_tmp to files_to_move
                files_to_move.update(files_to_move_tmp)
            except OverlayNotFoundError as e:
                # files_to_copy not updated, folder skipped
                if relpath:
                    nb_str = os.path.join(name, relpath)
                    logger.info(
                        "Could not resolve file '{}' in folder "
                        "'{}', notebooks will not be "
                        "delivered".format(str(e), nb_str)
                    )
    try:
        # exclude root __init__.py from copy, if it exists
        files_to_copy.pop(os.path.join(src_path, "__init__.py"))
    except KeyError:
        pass
    try:
        if not files_to_copy:
            logger.info(
                "The notebooks module '{}' could not be delivered. "
                "The module has no notebooks, or no valid overlays "
                "were found".format(name)
            )
        else:
            _copy_and_move_files(files_to_copy, files_to_move)
    except (Exception, KeyboardInterrupt) as e:
        # roll-back copy
        logger.info(
            "Exception detected. Cleaning up as the delivery process "
            "did not complete..."
        )
        _roll_back_copy(files_to_copy, files_to_move)
        raise e


class OverlayNotFoundError(Exception):
    """This exception is raised when an overlay for the target device could not
    be located."""

    pass


def _resolve_overlay_res_from_folder(
    device_name, overlay_res_folder, src_path, dst_path, rel_path, files_to_copy
):
    """Resolve ``overlay_res.ext`` file from ``overlay_res.ext.d`` folder,
    based on ``device_name``. Updates ``files_to_copy`` with the resolved file
    to use. If a ``overlay_res.ext.link`` file is found, resolution is skipped
    here. This is to avoid inspecting the ``overlay_res.ext.d`` folder twice.
    See ``_resolve_overlay_res_from_link()``.
    """
    overlay_res_filename = os.path.splitext(overlay_res_folder)[0]
    # Avoid checking a .d folder twice when also a
    # related .link file is found
    if not os.path.isfile(os.path.join(src_path, overlay_res_filename + ".link")):
        overlay_res_src_path = _find_local_overlay_res(
            device_name, overlay_res_filename, src_path
        )
        if overlay_res_src_path:
            overlay_res_dst_path = os.path.join(
                dst_path, rel_path, overlay_res_filename
            )
            files_to_copy[overlay_res_src_path] = overlay_res_dst_path
        else:
            raise OverlayNotFoundError(overlay_res_filename)


def _resolve_overlay_res_from_link(
    device_name,
    overlay_res_link,
    src_path,
    dst_path,
    rel_path,
    files_to_copy,
    files_to_move,
    logger,
):
    """Resolve ``overlay_res.ext`` file from ``overlay_res.ext.link`` file,
    based on ``device_name``. Updates ``files_to_copy`` with the resolved file
    to use if found locally (by inspecting ``overlay_res.ext.d`` folder), or
    updates ``files_to_move`` in case the file is downloaded.
    """
    overlay_res_filename = os.path.splitext(overlay_res_link)[0]
    overlay_res_dst_path = os.path.join(dst_path, rel_path, overlay_res_filename)
    overlay_res_src_path = _find_local_overlay_res(
        device_name, overlay_res_filename, src_path
    )

    if overlay_res_src_path:
        files_to_copy[overlay_res_src_path] = overlay_res_dst_path
    else:
        overlay_res_download_dict = _find_remote_overlay_res(
            device_name, os.path.join(src_path, overlay_res_link)
        )

        if overlay_res_download_dict:
            # attempt overlay_res.ext file download
            try:

                tmp_file = tempfile.mkstemp()[1]
                logger.info(
                    "Downloading file '{}'. This may take a while"
                    "...".format(overlay_res_filename)
                )
                _download_file(
                    overlay_res_download_dict["url"],
                    tmp_file,
                    overlay_res_download_dict["md5sum"],
                    overlay_res_download_dict.get("unpack"),
                )
                files_to_move[tmp_file] = overlay_res_dst_path
            except DownloadedFileChecksumError:
                raise OverlayNotFoundError(overlay_res_filename)
        else:
            raise OverlayNotFoundError(overlay_res_filename)


def _copy_and_move_files(files_to_copy, files_to_move):
    """Copy and move files and folders. ``files_to_copy`` and ``files_to_move``
    are expected to be dict where the key is the source path, and the value is
    destination path.
    """
    # copy files and folders
    for src, dst in files_to_copy.items():
        if os.path.isfile(src):
            mkpath(os.path.dirname(dst))
            copy_file(src, dst)
        else:
            copy_tree(src, dst)
    # and move files previously downloaded
    for src, dst in files_to_move.items():
        shutil.move(src, dst)


def _roll_back_copy(files_to_copy, files_to_move):
    """Roll-back previously performed copy of files and folders.
    ``files_to_copy`` and ``files_to_move`` are expected to be dict where the
    key is the source path, and the value is destination path.
    """
    for _, dst in files_to_copy.items():
        if os.path.isfile(dst):
            os.remove(dst)
            while len(os.listdir(os.path.dirname(dst))) == 0:
                os.rmdir(os.path.dirname(dst))
                dst = os.path.dirname(dst)
        elif os.path.isdir(dst):
            remove_tree(dst)
    for _, dst in files_to_move.items():
        if os.path.isfile(dst):
            os.remove(dst)
            while len(os.listdir(os.path.dirname(dst))) == 0:
                os.rmdir(os.path.dirname(dst))
                dst = os.path.dirname(dst)


def _find_local_overlay_res(device_name, overlay_res_filename, src_path):
    """Inspects ``overlay_res.ext.d` directory for an available
    ``overlay_res.ext`` file for  ``device_name``.
    Returns ``None`` if ``device_name`` is not found.

    If a ``overlay_res.ext`` file is also found, always return that one
    without doing any resolution based on ``device_name``.

    Parameters
    ----------
        device_name: str
            The target device name
        overlay_res_filename: str
            The target filename to resolve
        src_path: str
            The path where to perform this search
    """
    overlay_res_path = os.path.join(src_path, overlay_res_filename)
    if os.path.isfile(overlay_res_path):
        return overlay_res_path
    overlay_res_filename_split = os.path.splitext(overlay_res_filename)
    overlay_res_filename_ext = "{}.{}{}".format(
        overlay_res_filename_split[0], device_name, overlay_res_filename_split[1]
    )
    overlay_res_path = os.path.join(
        src_path, overlay_res_filename + ".d", overlay_res_filename_ext
    )
    if os.path.isfile(overlay_res_path):
        return overlay_res_path
    return None


def _find_remote_overlay_res(device_name, links_json_path):
    """Get download link for ``overlay_res.ext`` file and related checksum from
    ``overlay_res.ext.link`` json file, based on ``device_name``.

    The ``.link`` file is generally a dict of device names and associated url
    and md5sum.

    .. code-block:: python3
        {
            "device_1": {
                            "url": "https://link.to/overlay.xclbin",
                            "md5sum": "da1e100gh8e7becb810976e37875de38"
                        }.
            "device_2": {
                            "url": "https://link.to/overlay.xclbin",
                            "md5sum": "da1e100gh8e7becb810976e37875de38"
                        }
        }

    Expected return content from the ``.link`` json file is a dict with two
    entries:

    .. code-block:: python3

        {
            "url": "https://link.to/overlay.xclbin",
            "md5sum": "da1e100gh8e7becb810976e37875de38"
        }

    Returns `None` if ``device_name`` is not found.

    If the ``.link`` file contains a *url* and *md5sum* entries at the top
    level, these are returned and no device-based resolution is performed.

    Parameters
    ----------
        device_name: str
            The target device name
        links_json_path: str
            The full path to the ``.link`` json file
    """
    with open(links_json_path) as f:
        links = json.load(f)
    if "url" in links and "md5sum" in links:
        return {"url": links["url"], "md5sum": links["md5sum"]}
    if device_name in links:
        return links[device_name]
    return None


class DownloadedFileChecksumError(Exception):
    """This exception is raised when a downloaded file has an incorrect
    checksum."""

    pass


def _download_file(download_link, path, md5sum=None, unpack=False):
    """Download a file from the web.

    Parameters
    ----------
        download_link: str
            The download link to use
        path: str
            The path where to save the file. The path must include the target
            file
        md5sum: str or None
            If specified, it is used after download to check for correctness.
            Raises a `DownloadedFileChecksumError` exception when the checksum
            is incorrect, and deletes the downloaded file.
    """
    import urllib.request
    import hashlib
    import magic
    tmp_file = tempfile.mkstemp()[1]
    with urllib.request.urlopen(download_link) as response, \
            open(tmp_file, "wb") as out_file:
        data = response.read()
        out_file.write(data)
    if md5sum:
        file_md5sum = hashlib.md5()
        with open(tmp_file, "rb") as out_file:
            for chunk in iter(lambda: out_file.read(4096), b""):
                file_md5sum.update(chunk)
        if md5sum != file_md5sum.hexdigest():
            os.remove(tmp_file)
            raise DownloadedFileChecksumError("Incorrect checksum for file "
                                              "'{}'. The file has been "
                                              "deleted as a result".format(
                                                  tmp_file))
    if unpack:
        mime_type = magic.from_file(tmp_file, mime=True)
        for f in shutil.get_unpack_formats():
            if f[0] in mime_type:
                shutil.unpack_archive(tmp_file, path, format=f[0])
                return

    copy_file(tmp_file, path)
