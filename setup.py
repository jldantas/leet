# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name = "leet",
    version = "0.4.1",
    author = "Julio Dantas",
    description = "Leverage EDR for Execution of Things",
    url = "https://github.com/jldantas/leet",
    license = "Apache 2",
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
         "Development Status :: 3 - Alpha",
         "Environment :: Console",
         "Intended Audience :: Developers",
         "Intended Audience :: Information Technology",
         "License :: OSI Approved :: Apache Software License",
         "Operating System :: OS Independent",
         "Programming Language :: Python :: 3.6",
         "Programming Language :: Python :: 3 :: Only",
         "Topic :: Security"
    ],
    install_requires = ["tabulate", "cbapi", "apscheduler"],
    keywords = "leet edr",
    python_requires = ">=3.6",
    packages = find_packages(exclude=['contrib', 'docs', 'tests*']),
    entry_points = {
        "console_scripts" : ["leet_cli = leet.interfaces.cli:main"]
    }
)
