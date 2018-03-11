"""Setup module for zigpy"""

from setuptools import find_packages, setup

setup(
    name="zigpy",
    version="0.0.3",
    description="Library implementing a ZigBee stack",
    url="http://github.com/zigpy/zigpy",
    author="Russell Cloran",
    author_email="rcloran@gmail.com",
    license="GPL-3.0",
    packages=find_packages(exclude=['*.tests']),
    install_requires=[
        'pycryptodome',
        'crccheck',
    ],
    tests_require=[
        'pytest',
    ],
)
