![pynq_logo](https://github.com/Xilinx/PYNQ/raw/master/logo.png)
### version 0.1.1 

PYNQ-Utils is a repository containing utilities used in various other repos and projects across the PYNQ ecosystem. The tools are categorized into three sections:
* ``/runtime`` for utilities that are used in the PYNQ runtime, such as ```ReprDict``` which is used to pretty print dictionaries in Jupyter.
* ``/setup_utils`` for utilities that are used in the construction of python packages and to help in managing the PYNQ environment.
* ``/build_utils`` for utilities that are mainly used at build time when __constructing Overlays__. However, there are some utilities here that overlap with other sections, such as the XSAParser, which is also used by the PYNQ runtime for parsing the design metadata and bitstream.

## QuickStart

To install PYNQ-Utils use the following command:
```Bash
python3 -m pip install pynqutils 
```

## setup.py example

One place where PYNQ-Utils is frequently used is in the ```setup.py``` of projects that build upon PYNQ. 
```python
from pynqutils.setup_utils import build_py, find_version, extend_package, get_platform

data_files = []
extend_package(path=os.path.join(module_name, "notebooks"), data_files=data_files)

setup(
    name="pynq_helloworld",
    version=find_version('{}/__init__.py'.format("pynq_helloworld")),
    description="PYNQ example design supporting edge and PCIE boards",
    long_description="PYNQ HelloWorld example design",
    long_description_content_type='text/markdown',
    author='Xilinx PYNQ Development Team',
    author_email="pynq_support@xilinx.com",
    url='https://github.com/Xilinx/PYNQ-HelloWorld.git',
    license='BSD 3-Clause License',
    packages=find_packages(),
    package_data={
        "": data_files,
    },
    python_requires=">=3.6.0",
    install_requires=[
        "pynqutils",
        "matplotlib",
        "ipython"
    ],
    entry_points={
        "pynq.notebooks": [
            "pynq-helloworld = {}.notebooks.{}".format( "pynq_helloworld", get_platform())
        ]
    },
    cmdclass={"build_py": build_py}
)
```
As can be seen from the above snippet PYNQ-Utils contains lots of handy utilities for creating a ```setup.py``` script. Some examples from above are:
* ```find_version``` - used to find the verstion of the current project from the source
* ```extend_package``` - used to search directories to find files and directories to add to the package.
* ```get_platform``` - used to determine the current platform that the project is being installed onto, for instance, ```edge``` or ```pcie```.

A complete example of a ```setup.py``` using PYNQ-Utils can be found [here](https://github.com/STFleming/PYNQ-HelloWorld/blob/tests/setup.py).
