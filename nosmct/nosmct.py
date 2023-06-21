# SPDX-License-Identifier: MIT
# Author: Andrew Piroli
# Year: 2019-2023
import datetime as dtime
import multiprocessing as mp
import argparse
import os
import logging
import logging.handlers
from sys import argv, stdout, stderr
from concurrent.futures import ProcessPoolExecutor, wait
from time import perf_counter_ns
from netmiko import ConnectHandler  # type: ignore
from netmiko import NetmikoAuthenticationException, NetmikoTimeoutException
from constants import (
    NUM_THREADS_DEFAULT,
    THREAD_KILL_MSG,
    OperatingModes,
)
from FileOperations import (
    abspath,
    set_dir,
    load_jobfile,
    preload_jobfile,
    sanitize_filename,
)
from InventoryOperations import read_csv_config, get_inventory_from_lnms

"""
`p_config` dictionary contains configuration info on how the function itself should operate. It contains:
  mode is class OperatingMode, which tells the process how to interpret the jobs
  log_level is the configured logging level
  jobfile is the path to the jobfile incase it's not already loaded
  jobfile_cache is a dict with a cached list of commands for each device_type
  netmiko_debug is a path to a debug file, if present, it will log raw io for each device.
  output_dir is a path to the selected output directory. By default this is Output/<TIMESTAMP> but it may be overridden
"""
global p_config
p_config = {}


def run(info: dict, log_q: mp.Queue):
    """
    Worker thread running in process
    Creates a connection to the specified device, creates a folder for it, and runs throuigh the jobfile saving the results to the folder
    `info` dict contains device information like ip/hostname, device type, and login details
    `info` is passed directly to netmiko's `ConnectHandler` via kwargs dictionary unpacking
    """
    global p_config
    logger = logging.getLogger("nosmct")
    logger.addHandler(logging.handlers.QueueHandler(log_q))
    logger.setLevel(p_config["log_level"])
    original_directory = p_config["output_dir"]
    mode = p_config["mode"]
    jobfile = p_config["jobfile"]
    jobfile_cache = p_config["jobfile_cache"]
    #
    host = info["host"]
    logger.info(f"running - {host}")
    # Configure logging for netmiko
    nm_logger = logging.getLogger("netmiko")
    # Remove their default handler because it doesn't really work with my crappy logging sytstem I cooked up
    nm_logger.removeHandler(nm_logger.handlers[0])
    if p_config["netmiko_debug"] is not None:
        nm_logger.setLevel(logging.DEBUG)
        nm_log_fh = logging.FileHandler(str(p_config["netmiko_debug"]) + f"{os.getpid()}.log")
        nm_logger.addHandler(nm_log_fh)
    else:
        nm_logger.addHandler(logging.NullHandler())
    nm_logger.propagate = False
    #
    if jobfile_cache:
        jobfile = jobfile_cache
    elif jobfile:
        jobfile = load_jobfile(jobfile)
    else:
        jobfile = ()
    # Setup done, start actually working on the task at hand
    try:
        with ConnectHandler(**info) as connection:
            # This should probably have it's own try/except in case the enable doesn't work
            # But most exec commands and privileged anyway, and config modes certainly are
            # So dying hard here is acceptable to me.
            connection.enable()
            hostname = sanitize_filename(connection.find_prompt().split("#")[0])
            if mode != OperatingModes.SaveOnlyMode:
                set_dir(original_directory / hostname)
            logger.debug(f"run: Found hostname: {hostname} for {host}")
            if mode == OperatingModes.YoinkMode:
                for cmd in jobfile:
                    filename = f"{sanitize_filename(cmd)}.txt"
                    logger.debug(f"run: Got filename: {filename} for {host}")
                    with open(filename, "w") as output_file:
                        output_file.write(connection.send_command(cmd))
            elif mode == OperatingModes.YeetMode:
                # Filename here is not derived from any user controlled source, no need to run it through the sanitizer
                filename = "configset.txt"
                logger.debug(f"run: Got filename: {filename} for {host}")
                try:
                    with open(filename, "w") as output_file:
                        output_file.write(connection.send_config_set(jobfile))
                except NetmikoTimeoutException:
                    # Pass this up to the outer try/except
                    raise
                finally:
                    # No matter what happens, I don't want to leave a device without at least trying to save the config
                    connection.save_config()
            elif mode == OperatingModes.SaveOnlyMode:
                connection.save_config()
                logger.info(f"Saved config for {host}")
            else:
                logger.critical(f"Unhandled Operating Mode: {mode = }")
                raise RuntimeError("Unhandled Operating Mode: {mode = }")
    except (NetmikoTimeoutException, NetmikoAuthenticationException) as err:
        logger.critical(f"Exception in netmiko connection: {type(err).__name__}: {err}")
    except OSError as err:
        logger.critical(f"Error writing file: {type(err).__name__}: {err}")
    except Exception as err:
        logger.critical(f"Unknown exception: {type(err).__name__}: {err}")
    finally:
        os.chdir(original_directory)
    logger.info(f"finished -  {host}")


def handle_arguments() -> argparse.Namespace:
    """
    Collects and parses command line arguments
    """
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
    mode_selection.add_argument(
        "--save-only",
        action="store_true",
        help="Save only mode, just saves running-config",
    )
    inventory_selection = parser.add_mutually_exclusive_group(required=True)
    inventory_selection.add_argument("-i", "--inventory", help="CSV inventory file to load.")
    inventory_selection.add_argument(
        "-l", "--librenms-config", help="JSON config file for LibreNMS inventory"
    )
    parser.add_argument(
        "-j",
        "--jobfile",
        help="The file containing commands to send to the NOS",
        required=("--save-only" not in argv),
    )
    parser.add_argument("-t", "--threads", help="The number of devices to connect to at once.")
    parser.add_argument("-o", "--output-dir", help="Override the output directory")
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
    output_config.add_argument("-q", "--quiet", help="Suppress most output", action="store_true")
    output_config.add_argument("-v", "--verbose", help="Enable verbose output", action="store_true")
    return parser.parse_args()


def main():
    """The entry point for interactive use (the only supported use as of now)
    1) Collect command line arguments
    2) Configure itself from parsed command line args
    3) Read configuration files given
    4) Creates output directories
    5) Create and start process pool
    6) Spinlock until process pool completes or Ctrl-C is received
    7) Cleanup and exit.
    """
    global p_config
    start = perf_counter_ns()
    args = handle_arguments()
    log_level = logging.INFO
    if args.quiet:
        log_level = logging.CRITICAL
    if args.verbose:
        log_level = logging.DEBUG
    log_q = mp.Manager().Queue(-1)
    logging_process = mp.Process(target=out_of_process_logger, args=(log_q, log_level))
    logging_process.start()
    logger = logging.getLogger("nosmct")
    logger.addHandler(logging.handlers.QueueHandler(log_q))
    logger.setLevel(log_level)
    logger.info("Copyright Andrew Piroli 2019-2020")
    logger.info("MIT License\n")
    if args.yeet:
        selected_mode = OperatingModes.YeetMode
    elif args.yoink:
        selected_mode = OperatingModes.YoinkMode
    elif args.save_only:
        selected_mode = OperatingModes.SaveOnlyMode
    else:
        logger.critical("No operating mode selected from command line args")
        raise RuntimeError("No operating mode selected from command line args")
    logger.info(f"Running in operating mode: {selected_mode}")
    # TODO argparse can do validation (future self, you want to subclass `argparse.Action` override __call__)
    # Not sure it's worth it just yet, I'd even be fine crashing with invalid input especially since I *only* verify this one
    try:
        NUM_THREADS = int(args.threads) if args.threads else NUM_THREADS_DEFAULT
        if NUM_THREADS < 1:
            raise RuntimeError(f"User input: {NUM_THREADS} - below 1, can not create less than 1 processes.")
    except (ValueError, RuntimeError) as err:
        logger.critical(f"NUM_THREADS out of range: setting to default value of {NUM_THREADS_DEFAULT}")
        logger.debug(f"{repr(err)}")
        NUM_THREADS = NUM_THREADS_DEFAULT
    if args.inventory:
        config = read_csv_config(abspath(args.inventory))
    elif args.librenms_config:
        config = get_inventory_from_lnms(abspath(args.librenms_config))
        # If there's a problem (or missing deps), InventoryOps will notify the user and return None.
        if not config:
            return
    if args.jobfile:
        args.jobfile = abspath(args.jobfile)
    netmiko_debug_file = abspath(".") / "netmiko." if args.debug_netmiko else None
    preloaded_jobfile = preload_jobfile(args.jobfile) if not args.no_preload else None
    start_dir = abspath(".")
    if args.output_dir:
        output_dir = abspath(args.output_dir)
    else:
        output_dir = abspath("Output") / dtime.datetime.now().strftime("%Y-%m-%d %H.%M")
    if selected_mode != OperatingModes.SaveOnlyMode:
        set_dir(output_dir)
    p_config.update(
        {
            "mode": selected_mode,
            "log_level": log_level,
            "netmiko_debug": netmiko_debug_file,
            "jobfile": args.jobfile,
            "jobfile_cache": preloaded_jobfile,
            "output_dir": output_dir,
        }
    )
    # Stackoverflow https://stackoverflow.com/a/63495323
    # CC-BY-SA 4.0
    # By: geitda https://stackoverflow.com/users/14133684/geitda
    # Hopefully this improves Ctrl-C performance....
    with ProcessPoolExecutor(max_workers=NUM_THREADS) as ex:
        futures = [ex.submit(run, creds, log_q) for creds in config]
        done, not_done = wait(futures, timeout=0)
        try:
            while not_done:
                freshly_done, not_done = wait(not_done, timeout=0.5)
                done |= freshly_done
        except KeyboardInterrupt:
            for future in not_done:
                _ = future.cancel()
            logger.critical("Jobs cancelled, please wait for remaining jobs to finish.")
            _ = wait(not_done, timeout=None)
    # End Stackoverflow code
    os.chdir(start_dir)
    # We are back where we started
    end = perf_counter_ns()
    elapsed = round((end - start) / 1000000, 3)
    logger.info(f"Time Elapsed: {elapsed}ms")
    log_q.put(THREAD_KILL_MSG)
    logging_process.join()


def out_of_process_logger(log_q, level):
    logging.basicConfig(level=level)
    logger = logging.getLogger("nosmct")
    logger.debug("Logger: Initialized")
    while True:
        try:
            record = log_q.get()
            if record == THREAD_KILL_MSG:
                break
            logger = logging.getLogger(record.name)
            logger.handle(record)
        except Exception:
            import traceback

            logger.critical("Logging process failed")
            logger.critical(print(traceback.format_exc()))
            break
        finally:
            stdout.flush()
            stderr.flush()


if __name__ == "__main__":
    main()
