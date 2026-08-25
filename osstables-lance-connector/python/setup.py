#!/usr/bin/env python
"""Setup module for the OSS Tables connector for Lance."""

import os
import re

from setuptools import find_packages, setup

PACKAGE = "osstables_lance_connector"
DESCRIPTION = "Alibaba Cloud OSS Tables connector for Lance."
AUTHOR = "Alibaba Cloud"
URL = "https://github.com/aliyun/oss-connector-for-ai-ml"

TOPDIR = os.path.dirname(os.path.abspath(__file__))


def read_version():
    """Read __version__ from the package without importing it."""
    init_path = os.path.join(TOPDIR, "src", PACKAGE, "__init__.py")
    with open(init_path, encoding="utf-8") as fp:
        match = re.search(r'^__version__ = "([^"]+)"', fp.read(), re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to find __version__ in {}".format(init_path))
    return match.group(1)


with open(os.path.join(TOPDIR, "README.md"), encoding="utf-8") as fp:
    LONG_DESCRIPTION = fp.read()

requires = [
    "lance-namespace>=0.8.0",
    "lance-namespace-urllib3-client>=0.8.0",
    "urllib3>=1.26",
]

setup(
    name="osstables-lance-connector",
    version=read_version(),
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    author=AUTHOR,
    license="MIT",
    url=URL,
    keywords=["aliyun", "oss", "osstables", "lance", "namespace"],
    package_dir={"": "src"},
    packages=find_packages(where="src", exclude=["tests*"]),
    platforms="any",
    install_requires=requires,
    extras_require={"dev": ["pytest>=7.0.0"]},
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries",
    ],
)
