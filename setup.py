"""Setup module for zigpy"""

import pathlib

from setuptools import find_packages, setup

import zigpy

REQUIRES = [
    "aiohttp",
    "aiosqlite>=0.16.0",
    "async_timeout",
    "crccheck",
    "cryptography",
    'importlib_resources; python_version<"3.9"',
    "voluptuous",
    'pyserial-asyncio; platform_system!="Windows"',
    'pyserial-asyncio!=0.5; platform_system=="Windows"',
    "yarl",
]

setup(
    name="zigpy",
    version=zigpy.__version__,
    description="Library implementing a ZigBee stack",
    long_description=(pathlib.Path(__file__).parent / "README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/zigpy/zigpy",
    author="Russell Cloran",
    author_email="rcloran@gmail.com",
    license="GPL-3.0",
    packages=find_packages(exclude=["tests", "tests.*"]),
    install_requires=REQUIRES,
    python_requires=">=3.8",
    package_data={"": ["appdb_schemas/schema_v*.sql"]},
)
