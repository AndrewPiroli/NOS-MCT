# Andrew Piroli (c)2019-2020
#  MIT LICENSE  #
import datetime as dtime
import shutil
import multiprocessing as mp
import argparse
import os
import logging
import mctlogger
from queue import Empty as QEmptyException
from time import sleep
from typing import Any
from concurrent.futures import ProcessPoolExecutor
from netmiko import ConnectHandler  # type: ignore
from enum import Enum, auto
from FileOperations import (
    abspath,
    create_filename,
    set_dir,
    load_jobfile,
    read_config,
    preload_jobfile,
)


class OperatingModes(Enum):
    YeetMode = auto()  # We are sending configurations to the devices
    YoinkMode = auto()  # We are pulling configurations/status from the devices


def run(info: dict, p_config: dict):
    """
    Worker thread running in process
    Responsible for creating the connection to the device, finding the hostname, running the jobs, and saving them to the current directory.
    info dict contains device information like ip/hostname, device type, and login details
    p_config dictionary contains configuration info on how the function itself should operate. It contains:
      result_q is a proxy to a Queue where filename information is pushed so another thread can organize the files into the correct folder
      log_q is a queue to place log messages
      jobfile is the path to the jobfile incase it's not already loaded
      jobfile_cache is a dict with a cached list of commands for each device_type
    """
    mode = p_config["mode"]
    log_q = p_config["log_queue"]
    result_q = p_config["result_queue"]
    host = info["host"]
    #device_type = info["device_type"]
    jobfile = p_config["jobfile"]
    jobfile_cache = p_config["jobfile_cache"]
    log_q.put(f"warning running - {host}")
    nm_logger = logging.getLogger("netmiko")
    nm_logger.removeHandler(nm_logger.handlers[0])
    jobfile = jobfile_cache if jobfile_cache is not None else load_jobfile(jobfile)
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
            for cmd in jobfile:
                filename = create_filename(hostname, cmd)
                log_q.put(f"debug run: Got filename: {filename} for {host}")
                try:
                    with open(filename, "w") as output_file:
                        output_file.write(connection.send_command(cmd))
                    result_q.put(f"{hostname} {filename}")
                except Exception as e:
                    log_q.put(f"warning Error writing output file for {hostname}!")
                    log_q.put(f"debug {str(e)}")
        else:  # mode == OperatingModes.YeetMode
            filename = create_filename(hostname, "configset")
            log_q.put(f"debug run: Got filename: {filename} for {host}")
            try:
                with open(filename, "w") as output_file:
                    output_file.write(connection.send_config_set(jobfile))
                result_q.put(f"{hostname} {filename}")
            except Exception as e:
                log_q.put(f"warning Error writing output file for {hostname}!")
                log_q.put(f"debug {str(e)}")
            finally:
                connection.save_config()
    log_q.put(f"warning finished -  {host}")


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
            item = file_list.get(block=True, timeout=5)
            if item == "CY-DONE":
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
    logging_process = mp.Process(target=mctlogger.helper, args=(log_q, log_level))
    logging_process.start()
    log_q.put("warning Copyright Andrew Piroli 2019-2020")
    log_q.put("warning MIT License")
    log_q.put("warning ")
    selected_mode = OperatingModes.YeetMode if args.yeet else OperatingModes.YoinkMode
    log_q.put(f"warning Running in operating mode: {selected_mode}")
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
    preloaded_jobfile = (
        preload_jobfile(args.jobfile, log_q) if not args.no_preload else None
    )
    result_q = manager.Queue()
    p_config = {
        "mode": selected_mode,
        "result_queue": result_q,
        "log_queue": log_q,
        "netmiko_debug": netmiko_debug_file,
        "jobfile": args.jobfile,
        "jobfile_cache": preloaded_jobfile,
    }
    organization_thread = mp.Process(
        target=organize,
        args=(
            result_q,
            log_q,
        ),
    )
    organization_thread.start()
    with ProcessPoolExecutor(max_workers=NUM_THREADS_MAX) as ex:
        futures = [ex.submit(run, creds, p_config) for creds in config]
    result_q.put("CY-DONE")
    organization_thread.join()
    os.chdir("..")
    os.chdir("..")
    end = dtime.datetime.now()
    elapsed = (end - start).total_seconds()
    log_q.put(f"warning Time Elapsed: {elapsed}")
    log_q.put("die")
    logging_process.join()


if __name__ == "__main__":
    main()
