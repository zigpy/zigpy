"""Setup module for zigpy"""

from os import path

from setuptools import find_packages, setup
import zigpy

this_directory = path.join(path.abspath(path.dirname(__file__)))
with open(path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="zigpy",
    version=zigpy.__version__,
    description="Library implementing a ZigBee stack",
    url="http://github.com/zigpy/zigpy",
    author="Russell Cloran",
    author_email="rcloran@gmail.com",
    license="GPL-3.0",
    packages=find_packages(exclude=["*.tests"]),
    install_requires=["aiohttp", "crccheck", "pycryptodome", "voluptuous"],
    tests_require=["asynctest", "pytest"],
)
