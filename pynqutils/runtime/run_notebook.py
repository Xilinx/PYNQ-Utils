# Copyright (C) 2022 Xilinx, Inc
# SPDX-License-Identifier: BSD-3-Clause

import json
import os
import shutil
import tempfile

_function_text = """
import json

def _default_repr(obj):
    return repr(obj)

def _resolve_global(name):
    g = globals()
    return g[name] if name in g else None

"""


class NotebookResult:
    """Class representing the result of executing a notebook

    Contains members with the form ``_[0-9]*`` with the output object for
    each cell or ``None`` if the cell did not return an object.

    The raw outputs are available in the ``outputs`` attribute. See the
    Jupyter documentation for details on the format of the dictionary

    """

    def __init__(self, nb):
        self.outputs = [c["outputs"] for c in nb["cells"] if c["cell_type"] == "code"]
        objects = json.loads(self.outputs[-1][0]["text"])
        for i, o in enumerate(objects):
            setattr(self, "_" + str(i + 1), o)


def _create_code(num):
    call_line = "print(json.dumps([{}], default=_default_repr))".format(
        ", ".join(("_resolve_global('_{}')".format(i + 1) for i in range(num)))
    )
    return _function_text + call_line


def run_notebook(notebook, root_path=".", timeout=30, prerun=None):
    """Run a notebook in Jupyter

    This function will copy all of the files in ``root_path`` to a
    temporary directory, run the notebook and then return a
    ``NotebookResult`` object containing the outputs for each cell.

    The notebook is run in a separate process and only objects that
    are serializable will be returned in their entirety, otherwise
    the string representation will be returned instead.

    Parameters
    ----------
    notebook : str
        The notebook to run relative to ``root_path``
    root_path : str
        The root notebook folder (default ".")
    timeout : int
        Length of time to run the notebook in seconds (default 30)
    prerun : function
        Function to run prior to starting the notebook, takes the
        temporary copy of root_path as a parameter

    """
    import nbformat
    from nbconvert.preprocessors import ExecutePreprocessor

    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "work")
        notebook_dir = os.path.join(workdir, os.path.dirname(notebook))
        shutil.copytree(root_path, workdir)
        if prerun is not None:
            prerun(workdir)
        fullpath = os.path.join(workdir, notebook)
        with open(fullpath, "r") as f:
            nb = nbformat.read(f, as_version=4)
        ep = ExecutePreprocessor(kernel_name="python3", timeout=timeout)
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        nb["cells"].append(
            nbformat.from_dict(
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": _create_code(len(code_cells)),
                }
            )
        )
        ep.preprocess(nb, {"metadata": {"path": notebook_dir}})
        return NotebookResult(nb)
