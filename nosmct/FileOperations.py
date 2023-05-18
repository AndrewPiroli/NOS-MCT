# SPDX-License-Identifier: MIT
# Author: Andrew Piroli
# Year: 2021-2022
import pathlib
from typing import Iterator, List, Union, Optional
import os
import logging

# These characters/strings are illegal or their usage is discouraged on Windows, but could appear in a command name or device hostname.
illegals = list(' <>:\\/|?*$"')
illegals.extend(["CON", "PRN", "AUX", "NUL", "COM", "LPT", ".."])
illegals.extend([chr(i) for i in range(0, 32)])


def abspath(name: Union[str, pathlib.Path]) -> pathlib.Path:
    """Return a absolute Path object given an existing Path object or a string representing a path"""
    return pathlib.Path(name).absolute()


def sanitize_filename(filename: str) -> str:
    """
    Removes illegal characters for filenames, mainly for Windows support. No host platform detection though, all platforms must suffer.
    All files with derived names should be run through this filter before creation.
    """
    for illegal_string in illegals:
        filename = filename.replace(illegal_string, "_")
    return filename


def set_dir(name: Union[str, pathlib.Path]):
    """
    Helper function to create (and handle existing) folders and change directory to them automatically.
    """
    logger = logging.getLogger("nosmct")
    try:
        abspath(name).mkdir(parents=True, exist_ok=True)
        logger.debug(f"set_dir: abspath({name}).mkdir()")
    except Exception as e:
        logger.warning(
            f"Could not create {name} directory in {os.getcwd()}\nReason {e}"
        )
    try:
        os.chdir(name)
        logger.debug(f"set_dir: os.chdir({name})")
    except Exception as e:
        logger.warning(
            f"Could not change to {name} directory from {os.getcwd()}\nReason {e}"
        )


def load_jobfile(filename: pathlib.Path) -> Iterator[str]:
    """Generator for reading simple text files"""
    with open(
        filename,
        "r",
        newline="",
    ) as joblist:
        for job_entry in joblist:
            yield job_entry.strip()


def preload_jobfile(
    jobfile: Optional[pathlib.Path],
) -> Optional[List[str]]:
    """
    Like load_jobfile, but consumes the generator fully so the entire file may be cached.
    """
    logger = logging.getLogger("nosmct")
    if not jobfile:
        return None
    result = list(load_jobfile(jobfile))
    logger.debug(f"Added {jobfile} to cache")
    return result
