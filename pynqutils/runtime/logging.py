# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import logging

class _PynqLoggingFormatter(logging.Formatter):
    FORMATS = {
        logging.ERROR: "ERROR: %(msg)s",
        logging.WARNING: "WARNING: %(msg)s",
        logging.DEBUG: "DEBUG: %(module)s: %(lineno)d: %(msg)s",
        "DEFAULT": "%(msg)s",
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMATS["DEFAULT"])
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_logger(level=logging.INFO, force_lvl=False):
    """Returns an instance of the pynq.utils logger.

    Parameters
    ----------
        level: str or int
            String or integer constant representing the logging level following
            Python's logging standard levels. By default, the level is not
            updated if the current level is higher, unless `force_lvl` is set
            to `True`.
        force_lvl: bool
            If `True`, sets the logging level to `level` in any case.
    """
    levels = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
    }

    logger = logging.getLogger(__name__)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(_PynqLoggingFormatter())
        logger.addHandler(ch)
    logger_lvl = logger.getEffectiveLevel()
    if type(level) is str:
        level = levels[level.lower()]
    if level > logger_lvl or force_lvl:
        logger.setLevel(level)
    return logger
