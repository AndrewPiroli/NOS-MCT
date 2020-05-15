# Andrew Piroli (c)2019-2020
#  MIT LICENSE  #
import datetime as time
import shutil
import multiprocessing as mp
import argparse
import csv
import os
import logging
import pathlib
import threading
from typing import Iterator
from multiprocessing.managers import BaseProxy
from concurrent.futures import ProcessPoolExecutor
from netmiko import ConnectHandler


def abspath(name: str):
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


def run(info: list, result_q: mp.managers.BaseProxy, log_level: int, shows_folder: pathlib.Path):
    """
    Worker thread running in process
    Responsible for creating the connection to the device, finding the hostname, running the shows, and saving them to the current directory.
    info list contains device information like ip/hostname, device type, and login details
    result_q is a proxy to a Queue where filename information is pushed so another thread can organize the files into the correct folder
    log_level is either logging.WARNING, logging.DEBUG, or logging.CRITICAL depending on the verbosity chosen by the user
    shows_folder is a path to the folder that contains the commands to run for every device type - this was added to fix Linux
    """
    logging.basicConfig(format="", level=log_level)
    host = info[0]
    username = info[1]
    password = info[2]
    secret = info[3]
    device_type = info[4]
    shows = load_shows_from_file(device_type, shows_folder)
    logging.warning(f"running - {host} {username}")
    with ConnectHandler(
        device_type=device_type,
        host=host,
        username=username,
        password=password,
        secret=secret,
    ) as connection:
        connection.enable()
        # TODO: FIXME: Other vendors might not use a #
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
    logging.warning(f"Yoinker: finished host {host}")


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


def read_config(filename: pathlib.Path) -> Iterator[list]:
    """
    Generator function to processes the CSV config file. Handles the various CSV formats and removes headers.
    """
    with open(filename, "r") as config_file:
        dialect = csv.Sniffer().sniff(config_file.read(1024))  # Detect CSV style
        config_file.seek(0)  # Reset read head to beginning of file
        reader = csv.reader(config_file, dialect)
        _ = next(reader)  # Skip the header
        for config_entry in reader:
            yield config_entry


def organize(file_list: mp.managers.BaseProxy):
    """
    Responsible for taking the list of filenames of shows, creating folders, and renaming the shows into the correct folder.

    Process:

    1) Pulls a string off the queue in the format of '{Hostname} {Filename}'
    2) For each element, split the string between the hostname and filename
    3) Create a folder (set_dir) for the hostname
    4) The filename has an extra copy of the hostname, which is stripped off.
    5) Move+rename the file from the root dir into the the folder for the hostname
    """
    while True:
        try:
            item = file_list.get(block=True)
            if item == "CY-DONE":
                return
        except Exception as e:
            logging.warning("Error pulling from queue: {e}")
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
    start = time.datetime.now()
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
    set_dir(time.datetime.now().strftime("%Y-%m-%d %H.%M"))
    result_q = mp.Manager().Queue()
    organization_thread = threading.Thread(target=organize, args=(result_q,))
    organization_thread.start()
    with ProcessPoolExecutor(max_workers=NUM_THREADS_MAX) as ex:
        for creds in config:
            ex.submit(run, creds, result_q, log_level, shows_folder)
    result_q.put("CY-DONE")
    organization_thread.join()
    os.chdir("..")
    os.chdir("..")
    end = time.datetime.now()
    elapsed = (end - start).total_seconds()
    logging.warning(f"Time Elapsed: {elapsed}")


if __name__ == "__main__":
    main()
