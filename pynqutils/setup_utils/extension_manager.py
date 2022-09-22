# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import pkg_resources
import atexit

class ExtensionsManager:
    """Utility class to manage a list of available extensions registered for
    discovery.

    Parameters
    ----------
        package_name: str
            Name of the package to inspect for extensions
    """
    def __init__(self, package_name):
        self.package_name = package_name
        self.list = [ext for ext in
                     pkg_resources.iter_entry_points(self.package_name)]
        atexit.register(pkg_resources.cleanup_resources, force=True)

    @staticmethod
    def extension_path(extension_name):
        """Return the source path of the given extension name."""
        # Define monkey patch for `pkg_resources.NullProvider.__init__` to use
        # `module.__path__` instead of `module.__file__`, as the latter does
        # not exist for namespace packages.
        # Workaround for https://github.com/pypa/setuptools/issues/1407
        def init(self, module):
            self.loader = getattr(module, "__loader__", None)
            module_path = [p for p in getattr(module, "__path__", "")][0]
            self.module_path = module_path
        # Temporarily apply monkey patch to
        # `pkg_resources.NullProvider.__init__`
        init_backup = pkg_resources.NullProvider.__init__
        pkg_resources.NullProvider.__init__ = init
        src_path = pkg_resources.resource_filename(extension_name, "")
        # Restore original `pkg_resources.NullProvider.__init__`
        pkg_resources.NullProvider.__init__ = init_backup
        return src_path

    @property
    def printable(self):
        """Return a list of extension names and related parent packages
        for printing.
        """
        return ["{} (source: {})".format(e.name, e.module_name.split(".")[0])
                for e in self.list]

    @property
    def paths(self):
        """Return a list of paths from the discovered extensions.
        """
        return [self.extension_path(e.module_name) for e in self.list]
