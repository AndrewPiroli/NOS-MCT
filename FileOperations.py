import pathlib
from typing import Iterator, List, Any
import os
import csv
import shutil
from queue import Empty as QEmptyException
import constants

# These characters/strings are illegal or their usage is discouraged on Windows, but could appear in a command name or device hostname.
illegals = list(' <>:\\/|?*$"')
illegals.extend(["CON", "PRN", "AUX", "NUL", "COM", "LPT", ".."])
illegals.extend([chr(i) for i in range(0, 32)])


def abspath(name: str) -> pathlib.Path:
    return pathlib.Path(name).absolute()


def sanitize_filename(filename: str) -> str:
    """
    Removes illegal characters for filenames
    """
    for illegal_string in illegals:
        filename = filename.replace(illegal_string, "_")
    return filename


def set_dir(name: str, log_q: Any):
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
    with open(
        filename,
        "r",
        newline="",
    ) as joblist:
        for job_entry in joblist:
            yield job_entry.strip()


def read_config(filename: pathlib.Path, log_q: Any) -> Iterator[dict]:
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
            contents = "".join(contents)
            config_file.seek(0)
        dialect = csv.Sniffer().sniff(contents)  # Detect CSV style
        del contents
        reader = csv.reader(config_file, dialect)
        header = next(reader)
        log_q.put(f"debug read_config: header: {header}")
        for config_entry in reader:
            yield dict(zip(header, config_entry))


def preload_jobfile(
    jobfile: pathlib.Path,
    log_q: Any,
) -> List[str]:
    """
    Load the job file beforehand and put them in a Proxied list. This lets each process grab the list from memory than spending disk IOPS on it
    """
    result = list(load_jobfile(jobfile))
    log_q.put(f"debug Added {jobfile} to cache")
    return result
