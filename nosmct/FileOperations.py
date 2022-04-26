import pathlib
from typing import Iterator, List, Union, Optional
import os
import csv
import shutil
from queue import Empty as QEmptyException
import constants
from multiprocessing import Queue

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


def set_dir(name: Union[str, pathlib.Path], log_q: Queue):
    """
    Helper function to create (and handle existing) folders and change directory to them automatically.
    """
    try:
        abspath(name).mkdir(parents=True, exist_ok=True)
        log_q.put(f"debug set_dir: abspath({name}).mkdir()")
    except Exception as e:
        log_q.put(
            f"warning Could not create {name} directory in {os.getcwd()}\nReason {e}"
        )
    try:
        os.chdir(name)
        log_q.put(f"debug set_dir: os.chdir({name})")
    except Exception as e:
        log_q.put(
            f"warning Could not change to {name} directory from {os.getcwd()}\nReason {e}"
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


def read_config(filename: pathlib.Path, log_q: Queue) -> Iterator[dict]:
    """
    Generator function to processes the CSV config file. Handles the various CSV formats and stitches the header onto each entry.
    """
    with open(filename, "r") as config_file:
        log_q.put(f"debug read_config: filename: {filename}")
        try:
            contents = [
                next(config_file) for _ in range(2)
            ]  # Reading 2 lines of the CSV, is sufficient to detect style
        except StopIteration:  # Only occurs when the file has less than two lines....not a very useful file, but I'm ready for it
            pass
        finally:
            full_contents = "".join(contents)
            config_file.seek(0)
        dialect = csv.Sniffer().sniff(full_contents)  # Detect CSV style
        del contents, full_contents
        reader = csv.reader(config_file, dialect)
        header = next(reader)
        log_q.put(f"debug read_config: header: {header}")
        for config_entry in reader:
            yield dict(zip(header, config_entry))


def preload_jobfile(
    jobfile: Optional[pathlib.Path],
    log_q: Queue,
) -> Optional[List[str]]:
    """
    Like load_jobfile, but consumes the generator fully so the entire file may be cached.
    """
    if not jobfile:
        return None
    result = list(load_jobfile(jobfile))
    log_q.put(f"debug Added {jobfile} to cache")
    return result
