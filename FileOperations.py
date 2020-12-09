import pathlib
from typing import Iterator, List, Any
import os
import csv
import shutil
from queue import Empty as QEmptyException
from constants import (
    NUM_THREADS_DEFAULT,
    THREAD_KILL_MSG,
    OperatingModes,
)


def abspath(name: str) -> pathlib.Path:
    return pathlib.Path(name).absolute()


def create_filename(hostname: str, filename: str) -> str:
    """
    Outputs filenames with any illegal characters removed.
    """
    result = f"{hostname}_{filename}.txt"
    illegals = list(" <>:\\/|?*\0$")
    illegals.extend(["CON", "PRN", "AUX", "NUL", "COM", "LPT"])
    for illegal_string in illegals:
        result = result.replace(illegal_string, "_")
    return result


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
    Generator function to processes the CSV config file. Handles the various CSV formats and removes headers.
    """
    with open(filename, "r") as config_file:
        log_q.put(f"debug read_config: filename: {filename}")
        dialect = csv.Sniffer().sniff(config_file.read(1024))  # Detect CSV style
        config_file.seek(0)  # Reset read head to beginning of file
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


def organize(
    file_list: Any,
    log_q: Any,
):
    """
    Responsible for taking the list of filenames of jobs, creating folders, and renaming the job into the correct folder.

    Process:

    1) Pulls a string off the queue in the format of '{Hostname} {Filename}'
    2) For each element, split the string between the hostname and filename
    3) Create a folder (set_dir) for the hostname
    4) The filename has an extra copy of the hostname, which is stripped off.
    5) Move+rename the file from the root dir into the the folder for the hostname
    """
    log_q.put("debug Organize thread starting")
    other_exception_cnt = 0
    while True:
        try:
            item = file_list.get(block=True, timeout=1)
            if item == THREAD_KILL_MSG:
                log_q.put("debug Organize thread recieved done flag, closing thread")
                return
            other_exception_cnt = 0
        except QEmptyException:
            continue
        except Exception as e:
            log_q.put(f"warning Error pulling from queue: {e}")
            other_exception_cnt += 1
            if other_exception_cnt > 10:
                # If there are 10 errors (not incl Empty queue) in a row, something is hecked up, just give up
                log_q.put(
                    "critical ERROR: Big problemos inside organize(), just going to kill myself I guess..."
                )
                return
            continue
        original_dir = abspath(".")
        job_entry = item.split(" ")
        job_entry_hostname = job_entry[0]
        job_entry_filename = job_entry[1]
        log_q.put(
            f"debug Organize thread: job_entry_hostname: {job_entry_hostname} job_entry_filename: {job_entry_filename}"
        )
        try:
            destination = job_entry_filename.replace(f"{job_entry_hostname}_", "")
            log_q.put(f"debug Organize thread: destination: {destination}")
            set_dir(job_entry_hostname, log_q)
            shutil.move(f"../{job_entry_filename}", f"./{destination}")
            log_q.put(
                f"debug Organize thread: shutil.move(../{job_entry_filename}, ./{destination}"
            )
        except Exception as e:
            log_q.put(f"warning Error organizing {job_entry_filename}: {e}")
            continue
        finally:
            os.chdir(original_dir)
            log_q.put(f"debug Organize thread: finally: os.chdir({original_dir})")
