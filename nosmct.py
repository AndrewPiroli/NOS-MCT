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
import mctlogger
from queue import Empty as QEmptyException
from time import sleep
from typing import Iterator, Callable
from multiprocessing.managers import BaseProxy
from concurrent.futures import ProcessPoolExecutor
from netmiko import ConnectHandler
from enum import Enum, auto


class OperatingModes(Enum):
    YeetMode = auto()  # We are sending configurations to the devices
    YoinkMode = auto()  # We are pulling configurations/status from the devices


def mk_logger(q: BaseProxy, level: int, kill_flag: Callable[[], bool]):
    logger = mctlogger.mctlogger(q, {"kill_callback": kill_flag, "output_level": level})
    logger.runloop()


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


def run(info: dict, p_config: dict):
    """
    Worker thread running in process
    Responsible for creating the connection to the device, finding the hostname, running the shows, and saving them to the current directory.
    info dict contains device information like ip/hostname, device type, and login details
    p_config dictionary contains configuration info on how the function itself should operate. It contains:
      result_q is a proxy to a Queue where filename information is pushed so another thread can organize the files into the correct folder
      log_q is a queue to place log messages
      shows_folder is a path to the folder that contains the commands to run for every device type
      jobfile_cache is a dict with a cached list of commands for each device_type
    """
    mode = p_config["mode"]
    log_q = p_config["log_queue"]
    result_q = p_config["result_queue"]
    host = info["host"]
    device_type = info["device_type"]
    jobfile = p_config["jobfile"]
    jobfile_cache = p_config["jobfile_cache"]
    log_q.put(f"warning running - {host}")
    nm_logger = logging.getLogger("netmiko")
    nm_logger.removeHandler(nm_logger.handlers[0])
    if jobfile_cache is not None:
        jobfile = jobfile_cache
    else:
        log_q.put(
            f"debug Caching is disabled: load shows from file: device_type: {device_type}"
        )
        jobfile = load_shows_from_file(jobfile)
    if p_config["netmiko_debug"] is not None:
        nm_logger.setLevel(logging.DEBUG)
        nm_log_fh = logging.FileHandler(
            str(p_config["netmiko_debug"]) + f"{os.getpid()}.log"
        )
        nm_logger.addHandler(nm_log_fh)
    else:
        nm_logger.addHandler(logging.NullHandler())
    nm_logger.propagate = False
    with ConnectHandler(**info) as connection:
        connection.enable()
        hostname = connection.find_prompt().split("#")[0]
        log_q.put(f"debug run: Found hostname: {hostname} for {host}")
        if mode == OperatingModes.YoinkMode:
            for show in jobfile:
                filename = create_filename(hostname, show)
                log_q.put(f"debug run: Got filename: {filename} for {host}")
                try:
                    with open(filename, "w") as output_file:
                        output_file.write(connection.send_command(show))
                    result_q.put(f"{hostname} {filename}")
                except Exception as e:
                    log_q.put(f"warning Error writing show for {hostname}!")
                    log_q.put(f"debug {str(e)}")
        else:  # mode == OperatingModes.YeetMode
            filename = create_filename(hostname, "configset")
            log_q.put(f"debug run: Got filename: {filename} for {host}")
            try:
                with open(filename, "w") as output_file:
                    output_file.write(connection.send_config_set(jobfile))
                result_q.put(f"{hostname} {filename}")
            except Exception as e:
                log_q.put(f"warning Error writing show for {hostname}!")
                log_q.put(f"debug {str(e)}")
            finally:
                connection.save_config()
    log_q.put(f"warning finished -  {host}")


def set_dir(name: str, log_q: BaseProxy):
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


def load_shows_from_file(filename: pathlib.Path) -> Iterator[str]:
    """
    Generator to pull in shows for a given device type
    """
    with open(
        filename,
        "r",
        newline="",
    ) as show_list:
        for show_entry in show_list:
            yield show_entry.strip()


def read_config(filename: pathlib.Path, log_q: BaseProxy) -> Iterator[dict]:
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


def organize(file_list: BaseProxy, log_q: BaseProxy, joined_flag: Callable[[], bool]):
    """
    Responsible for taking the list of filenames of shows, creating folders, and renaming the shows into the correct folder.

    Process:

    1) Pulls a string off the queue in the format of '{Hostname} {Filename}'
    2) For each element, split the string between the hostname and filename
    3) Create a folder (set_dir) for the hostname
    4) The filename has an extra copy of the hostname, which is stripped off.
    5) Move+rename the file from the root dir into the the folder for the hostname
    """
    log_q.put("debug Organize thread starting")
    empty_count = 0
    other_exception_cnt = 0
    while True:
        try:
            item = file_list.get(block=True, timeout=1)
            if item == "CY-DONE":
                log_q.put("debug Organize thread recieved done flag, closing thread")
                return
            other_exception_cnt = 0
            empty_count = 0
        except QEmptyException:
            # The queue being empty is fine, as long as the worker processes haven't finished. so check if the main thread has set the flag before we care abt empty q's
            if joined_flag():
                empty_count += 1
                if empty_count >= 20:
                    # 20 attempts * 1 second each = 20 seconds with nothing on the queue, safe to say its borked somehow
                    log_q.put(
                        "critical ERROR: Queue is empty but thread still running, killing self now!"
                    )
                    return
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
        show_entry = item.split(" ")
        show_entry_hostname = show_entry[0]
        show_entry_filename = show_entry[1]
        log_q.put(
            f"debug Organize thread: show_entry_hostname: {show_entry_hostname} show_entry_filename: {show_entry_filename}"
        )
        try:
            destination = show_entry_filename.replace(f"{show_entry_hostname}_", "")
            log_q.put(f"debug Organize thread: destination: {destination}")
            set_dir(show_entry_hostname, log_q)
            shutil.move(f"../{show_entry_filename}", f"./{destination}")
            log_q.put(
                f"debug Organize thread: shutil.move(../{show_entry_filename}, ./{destination}"
            )
        except Exception as e:
            log_q.put(f"warning Error organizing {show_entry_filename}: {e}")
            continue
        finally:
            os.chdir(original_dir)
            log_q.put(f"debug Organize thread: finally: os.chdir({original_dir})")


def preload_jobfile(
    jobfile: pathlib.Path,
    manager: mp.Manager,
    log_q: BaseProxy,
) -> BaseProxy:
    """
    Load all of the show files beforehand and put them in a Proxied dict. This lets each process grab the list from memory than spending disk IOPS on it
    """
    result = manager.list()
    result = list(load_shows_from_file(jobfile))
    log_q.put(f"debug Added {jobfile} to cache")
    return result


def handle_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode_selection = parser.add_mutually_exclusive_group(required=True)
    mode_selection.add_argument(
        "--yeet",
        action="store_true",
        help="Yeet mode, push configurations to NOS",
    )
    mode_selection.add_argument(
        "--yoink",
        action="store_true",
        help="Yoink mode, pull configurations from NOS",
    )
    parser.add_argument(
        "-i", "--inventory", help="The inventory file to load.", required=True
    )
    parser.add_argument(
        "-j",
        "--jobfile",
        help="The file containing commands to send to the NOS",
        required=True,
    )
    parser.add_argument(
        "--confirm-yeet",
        help="Bypass confirmation prompt for yeet mode",
        action="store_true",
    )
    parser.add_argument(
        "-t", "--threads", help="The number of devices to connect to at once."
    )
    parser.add_argument(
        "--debug-netmiko",
        help="Advanced debuging, logs netmiko internals to a file",
        action="store_true",
    )
    parser.add_argument(
        "--no-preload",
        help="Disable caching for config files.",
        action="store_true",
    )
    output_config = parser.add_mutually_exclusive_group(required=False)
    output_config.add_argument(
        "-q", "--quiet", help="Suppress most output", action="store_true"
    )
    output_config.add_argument(
        "-v", "--verbose", help="Enable verbose output", action="store_true"
    )
    return parser.parse_args()


def confirm_yeet(mode: OperatingModes, confirmed: bool, log_q: BaseProxy) -> bool:
    """
    Yeeting configs onto the device is a dangerous op, make sure they know what they are doing so I feel a little better.
    """
    if mode == OperatingModes.YeetMode and not confirmed:
        log_q.put("critical YeetMode selected without confirmation")
        sleep(0.5)  # Time for log message
        attempt = 1
        while True:
            response = (
                input(
                    f"Attempt: {attempt} of 5. Do you confirm you are in yeet (config SEND) mode? [y/N]: "
                )
                .strip()
                .lower()
            )
            if response.startswith("y"):
                break
            if response.startswith("n"):
                return False
            else:
                attempt += 1
                if attempt > 5:
                    return False
    elif mode == OperatingModes.YoinkMode and confirmed:
        log_q.put("warning confirm-yeet option has no effect in YoinkMode")
    return True


def main():
    args = handle_arguments()
    start = dtime.datetime.now()
    log_level = logging.WARNING
    if args.quiet:
        log_level = logging.CRITICAL
    if args.verbose:
        log_level = logging.DEBUG
    manager = mp.Manager()
    log_q = manager.Queue()
    log_thread_killed_flag = False
    log_thread = threading.Thread(
        target=mk_logger, args=(log_q, log_level, lambda: log_thread_killed_flag)
    )
    log_thread.start()
    log_q.put("warning Copyright Andrew Piroli 2019-2020")
    log_q.put("warning MIT License")
    log_q.put("warning ")
    selected_mode = OperatingModes.YeetMode if args.yeet else OperatingModes.YoinkMode
    log_q.put(f"warning Running in operating mode: {selected_mode}")
    if not confirm_yeet(selected_mode, args.confirm_yeet, log_q):
        log_q.put("critical Aborting due to yeeting without consent.")
        log_thread_killed_flag = True
        sleep(1.5)
        import sys

        sys.exit()
    NUM_THREADS_MAX = 10
    if args.threads:
        try:
            NUM_THREADS_MAX = int(args.threads)
            if NUM_THREADS_MAX < 1:
                raise RuntimeError(
                    f"User input: {NUM_THREADS_MAX} - below 1, can not create less than 1 processes."
                )
        except (ValueError, RuntimeError) as err:
            log_q.put(
                "critical NUM_THREADS out of range: setting to default value of 10"
            )
            log_q.put(f"debug {repr(err)}")
            NUM_THREADS_MAX = 10
    args.inventory = abspath(args.inventory)
    config = read_config(abspath(args.inventory), log_q)
    args.jobfile = abspath(args.jobfile)
    set_dir("Output", log_q)
    set_dir(dtime.datetime.now().strftime("%Y-%m-%d %H.%M"), log_q)
    netmiko_debug_file = abspath(".") / "netmiko." if args.debug_netmiko else None
    preloaded_shows = preload_jobfile(args.jobfile, manager, log_q) if not args.no_preload else None
    result_q = manager.Queue()
    p_config = {
        "mode": selected_mode,
        "result_queue": result_q,
        "log_queue": log_q,
        "netmiko_debug": netmiko_debug_file,
        "jobfile": args.jobfile,
        "jobfile_cache": preloaded_shows,
    }
    org_thread_joined_flag = False
    organization_thread = threading.Thread(
        target=organize, args=(result_q, log_q, lambda: org_thread_joined_flag)
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
    log_q.put(f"warning Time Elapsed: {elapsed}")
    log_thread_killed_flag = True


if __name__ == "__main__":
    main()
