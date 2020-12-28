# Andrew Piroli (c)2019-2020
#  MIT LICENSE  #
import datetime as dtime
import multiprocessing as mp
import argparse
import os
import logging
import mctlogger
from typing import Any
from concurrent.futures import ProcessPoolExecutor, wait
from netmiko import ConnectHandler  # type: ignore
from netmiko import NetmikoAuthenticationException, NetmikoTimeoutException
from constants import (
    NUM_THREADS_DEFAULT,
    THREAD_KILL_MSG,
    OperatingModes,
)
from FileOperations import (
    abspath,
    create_filename,
    set_dir,
    load_jobfile,
    read_config,
    preload_jobfile,
    organize,
)


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
    try:
        with ConnectHandler(**info) as connection:
            connection.enable()
            hostname = connection.find_prompt().split("#")[0]
            log_q.put(f"debug run: Found hostname: {hostname} for {host}")
            if mode == OperatingModes.YoinkMode:
                for cmd in jobfile:
                    filename = create_filename(hostname, cmd)
                    log_q.put(f"debug run: Got filename: {filename} for {host}")
                    with open(filename, "w") as output_file:
                        output_file.write(connection.send_command(cmd))
                    result_q.put(f"{hostname} {filename}")
            else:  # mode == OperatingModes.YeetMode
                filename = create_filename(hostname, "configset")
                log_q.put(f"debug run: Got filename: {filename} for {host}")
                try:
                    with open(filename, "w") as output_file:
                        output_file.write(connection.send_config_set(jobfile))
                    result_q.put(f"{hostname} {filename}")
                finally:
                    connection.save_config()
    except (NetmikoTimeoutException, NetmikoAuthenticationException) as err:
        log_q.put(f"critical Exception in netmiko connection: {err}")
    except OSError as err:
        log_q.put(f"critical Error writing file: {err}")
    log_q.put(f"warning finished -  {host}")


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
    try:
        NUM_THREADS = int(args.threads) if args.threads else NUM_THREADS_DEFAULT
        if NUM_THREADS < 1:
            raise RuntimeError(
                f"User input: {NUM_THREADS} - below 1, can not create less than 1 processes."
            )
    except (ValueError, RuntimeError) as err:
        log_q.put(
            f"critical NUM_THREADS out of range: setting to default value of {NUM_THREADS_DEFAULT}"
        )
        log_q.put(f"debug {repr(err)}")
        NUM_THREADS = NUM_THREADS_DEFAULT
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
    # Stackoverflow https://stackoverflow.com/a/63495323
    # CC-BY-SA 4.0
    # By: geitda https://stackoverflow.com/users/14133684/geitda
    # Hopefully this improves Ctrl-C performance....
    with ProcessPoolExecutor(max_workers=NUM_THREADS) as ex:
        futures = [ex.submit(run, creds, p_config) for creds in config]
        done, not_done = wait(futures, timeout=0)
        try:
            while not_done:
                freshly_done, not_done = wait(not_done, timeout=0.5)
                done |= freshly_done
        except KeyboardInterrupt:
            for future in not_done:
                _ = future.cancel()
            log_q.put(
                "critical Jobs cancelled, please wait for remaining jobs to finish."
            )
            _ = wait(not_done, timeout=None)
    # End Stackoverflow code
    result_q.put(THREAD_KILL_MSG)
    organization_thread.join()
    os.chdir("..")
    os.chdir("..")
    end = dtime.datetime.now()
    elapsed = (end - start).total_seconds()
    log_q.put(f"warning Time Elapsed: {elapsed}")
    log_q.put(THREAD_KILL_MSG)
    logging_process.join()


if __name__ == "__main__":
    main()
