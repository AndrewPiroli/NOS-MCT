# Andrew Piroli (c)2019-2020
#  MIT LICENSE  #
import datetime as dtime
import shutil
import multiprocessing as mp
import argparse
import csv
import os
import logging
import pathlib
import threading
from queue import Empty as QEmptyException
from time import sleep
from typing import Iterator, Callable
from multiprocessing.managers import BaseProxy
from concurrent.futures import ProcessPoolExecutor
from netmiko import ConnectHandler


def abspath(name: str) -> pathlib.Path:
    return pathlib.Path(name).absolute()


def create_filename(hostname: str, filename: str) -> str:
    """
    Outputs filenames with any illegal characters removed.
    """
    illegals = list(" <>:\\/|?*\0$")
    illegals.extend(["CON", "PRN", "AUX", "NUL", "COM", "LPT"])
    for illegal_string in illegals:
        filename = filename.replace(illegal_string, "_")
    return f"{hostname}_{filename}.txt"


def run(info: dict, p_config: dict):
    """
    Worker thread running in process
    Responsible for creating the connection to the device, finding the hostname, running the shows, and saving them to the current directory.
    info dict contains device information like ip/hostname, device type, and login details
    p_config dictionary contains configuration info on how the function itself should operate. It contains:
      result_q is a proxy to a Queue where filename information is pushed so another thread can organize the files into the correct folder
      log_level is either logging.WARNING, logging.DEBUG, or logging.CRITICAL depending on the verbosity chosen by the user
      shows_folder is a path to the folder that contains the commands to run for every device type - this was added to fix Linux
    """
    result_q = p_config["queue"]
    log_level = p_config["log_level"]
    shows_folder = p_config["shows_folder"]
    host = info["host"]
    shows = load_shows_from_file(info["device_type"], shows_folder)
    logging.basicConfig(format="", level=log_level)
    logging.warning(f"running - {host}")
    with ConnectHandler(**info) as connection:
        connection.enable()
        hostname = connection.find_prompt().split("#")[0]
        for show in shows:
            filename = create_filename(hostname, show)
            try:
                with open(filename, "w") as show_file:
                    show_file.write(connection.send_command(show))
                result_q.put(f"{hostname} {filename}")
            except Exception as e:
                logging.warning(f"Error writing show for {hostname}!")
                logging.debug(str(e))
    logging.warning(f"finished -  {host}")


def set_dir(name: str):
    """
    Helper function to create (and handle existing) folders and change directory to them automatically.
    """
    try:
        abspath(name).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.warning(
            f"Could not create {name} directory in {os.getcwd()}\nReason {e}"
        )
    try:
        os.chdir(name)
    except Exception as e:
        logging.warning(
            f"Could not change to {name} directory from {os.getcwd()}\nReason {e}"
        )


def load_shows_from_file(device_type: str, shows_folder: pathlib.Path) -> Iterator[str]:
    """
    Generator to pull in shows for a given device type
    """
    show_file_list = shows_folder / f"shows_{device_type}.txt"
    with open(show_file_list, "r", newline="",) as show_list:
        for show_entry in show_list:
            yield show_entry.strip()


def read_config(filename: pathlib.Path) -> Iterator[dict]:
    """
    Generator function to processes the CSV config file. Handles the various CSV formats and removes headers.
    """
    with open(filename, "r") as config_file:
        dialect = csv.Sniffer().sniff(config_file.read(1024))  # Detect CSV style
        config_file.seek(0)  # Reset read head to beginning of file
        reader = csv.reader(config_file, dialect)
        header = next(reader)
        for config_entry in reader:
            yield dict(zip(header, config_entry))


def organize(file_list: mp.managers.BaseProxy, joined_flag: Callable[[], bool]):
    """
    Responsible for taking the list of filenames of shows, creating folders, and renaming the shows into the correct folder.

    Process:

    1) Pulls a string off the queue in the format of '{Hostname} {Filename}'
    2) For each element, split the string between the hostname and filename
    3) Create a folder (set_dir) for the hostname
    4) The filename has an extra copy of the hostname, which is stripped off.
    5) Move+rename the file from the root dir into the the folder for the hostname
    """
    empty_count = 0
    other_exception_cnt = 0
    while True:
        try:
            item = file_list.get(block=True, timeout=2)
            if item == "CY-DONE":
                return
            other_exception_cnt = 0
            empty_count = 0
        except QEmptyException:
            # The queue being empty is fine, as long as the worker processes haven't finished. so check if the main thread has set the flag before we care abt empty q's
            if joined_flag():
                empty_count += 1
                if empty_count >= 8:
                    # 8 attempts * 2 seconds each = 16 seconds with nothing on the queue, safe to say its borked somehow
                    logging.critical(
                        "ERROR: Queue is empty but thread still running, killing self now!"
                    )
                    return
            continue
        except Exception as e:
            logging.warning(f"Error pulling from queue: {e}")
            other_exception_cnt += 1
            if other_exception_cnt > 10:
                # If there are 10 errors (not incl Empty queue) in a row, something is hecked up, just give up
                logging.critical(
                    "ERROR: Big problemos inside organize(), just going to kill myself I guess..."
                )
                return
            continue
        original_dir = abspath(".")
        show_entry = item.split(" ")
        show_entry_hostname = show_entry[0]
        show_entry_filename = show_entry[1]
        try:
            destination = show_entry_filename.replace(f"{show_entry_hostname}_", "")
            set_dir(show_entry_hostname)
            shutil.move(f"../{show_entry_filename}", f"./{destination}")
        except Exception as e:
            logging.warning(f"Error organizing {show_entry_filename}: {e}")
            continue
        finally:
            os.chdir(original_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", help="The configuration file to load.")
    parser.add_argument(
        "-t", "--threads", help="The number of devices to connect to at once."
    )
    parser.add_argument(
        "-f",
        "--force",
        help="Allow setting NUM_THREADS to stupid levels",
        action="store_true",
    )
    output_config = parser.add_mutually_exclusive_group(required=False)
    output_config.add_argument(
        "-q", "--quiet", help="Suppress most output", action="store_true"
    )
    output_config.add_argument(
        "-v", "--verbose", help="Enable verbose output", action="store_true"
    )
    args = parser.parse_args()
    start = dtime.datetime.now()
    log_level = logging.WARNING
    if args.quiet:
        log_level = logging.CRITICAL
    if args.verbose:
        log_level = logging.DEBUG
    logging.basicConfig(format="", level=log_level)
    logging.warning("Copyright Andrew Piroli 2019-2020")
    logging.warning("MIT License")
    logging.warning("")
    NUM_THREADS_MAX = 10
    if args.threads:
        try:
            NUM_THREADS_MAX = int(args.threads)
            if NUM_THREADS_MAX < 1:
                raise RuntimeError(
                    f"User input: {NUM_THREADS_MAX} - below 1, can not create less than 1 processes."
                )
            if NUM_THREADS_MAX > 25:
                if not args.force:
                    raise RuntimeError(
                        f"User input: {NUM_THREADS_MAX} - over limit and no force flag detected - refusing to create a stupid amount of processes"
                    )
        except (ValueError, RuntimeError) as err:
            logging.critical("NUM_THREADS out of range: setting to default value of 10")
            logging.debug(repr(err))
            NUM_THREADS_MAX = 10
    if args.config:
        config = read_config(abspath(args.config))
    else:
        config = read_config(abspath("Cisco-Yoink-Default.config"))
    shows_folder = abspath(".") / "shows"
    set_dir("Output")
    set_dir(dtime.datetime.now().strftime("%Y-%m-%d %H.%M"))
    result_q = mp.Manager().Queue()
    p_config = {"queue": result_q, "log_level": log_level, "shows_folder": shows_folder}
    org_thread_joined_flag = (
        False  # A way to tell the thread we have joined() and are waiting on it.
    )
    organization_thread = threading.Thread(
        target=organize, args=(result_q, lambda: org_thread_joined_flag)
    )
    organization_thread.start()
    with ProcessPoolExecutor(max_workers=NUM_THREADS_MAX) as ex:
        for creds in config:
            ex.submit(run, creds, p_config)
    result_q.put("CY-DONE")
    org_thread_joined_flag = True
    organization_thread.join()
    os.chdir("..")
    os.chdir("..")
    end = dtime.datetime.now()
    elapsed = (end - start).total_seconds()
    logging.warning(f"Time Elapsed: {elapsed}")


if __name__ == "__main__":
    main()
