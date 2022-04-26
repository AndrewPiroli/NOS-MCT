# Andrew Piroli (c)2019-2021
#  MIT LICENSE  #
import datetime as dtime
import multiprocessing as mp
import argparse
import os
import logging
import mctlogger
from sys import argv
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
    set_dir,
    load_jobfile,
    read_config,
    preload_jobfile,
    sanitize_filename,
)


def run(info: dict, p_config: dict):
    """
    Worker thread running in process
    Creates a connection to the specified device, creates a folder for it, and runs throuigh the jobfile saving the results to the folder
    `info` dict contains device information like ip/hostname, device type, and login details
    `info` is passed directly to netmiko's `ConnectHandler` via kwargs dictionary unpacking
    `p_config` dictionary contains configuration info on how the function itself should operate. It contains:
      mode is class OperatingMode, which tells the process how to interpret the jobs
      log_queue is a queue to place log messages
      jobfile is the path to the jobfile incase it's not already loaded
      jobfile_cache is a dict with a cached list of commands for each device_type
      netmiko_debug is a path to a debug file, if present, it will log raw io for each device.
    """
    # Save the original directory, we chdir around and we need to come back because the process will
    # inherit it next time around (I dislike this behavior of ProcessPoolExecutor).
    # If it ever breaks, it can be moved to p_config, but I see no need to do that preemptively
    # because I don't really like having to pass in p_config (can this be a module level global? - I think so)
    original_directory = abspath(".")
    mode = p_config["mode"]
    log_q = p_config["log_queue"]
    jobfile = p_config["jobfile"]
    jobfile_cache = p_config["jobfile_cache"]
    #
    host = info["host"]
    log_q.put(f"warning running - {host}")
    # Configure logging for netmiko
    nm_logger = logging.getLogger("netmiko")
    # Remove their default handler because it doesn't really work with my crappy logging sytstem I cooked up
    nm_logger.removeHandler(nm_logger.handlers[0])
    if p_config["netmiko_debug"] is not None:
        nm_logger.setLevel(logging.DEBUG)
        nm_log_fh = logging.FileHandler(
            str(p_config["netmiko_debug"]) + f"{os.getpid()}.log"
        )
        nm_logger.addHandler(nm_log_fh)
    else:
        nm_logger.addHandler(logging.NullHandler())
    nm_logger.propagate = False
    #
    jobfile = jobfile_cache if jobfile_cache is not None else load_jobfile(jobfile)
    # Setup done, start actually working on the task at hand
    try:
        with ConnectHandler(**info) as connection:
            # This should probably have it's own try/except in case the enable doesn't work
            # But most exec commands and privileged anyway, and config modes certainly are
            # So dying hard here is acceptable to me.
            connection.enable()
            hostname = sanitize_filename(connection.find_prompt().split("#")[0])
            set_dir(original_directory / hostname, log_q)
            log_q.put(f"debug run: Found hostname: {hostname} for {host}")
            if mode == OperatingModes.YoinkMode:
                for cmd in jobfile:
                    filename = f"{sanitize_filename(cmd)}.txt"
                    log_q.put(f"debug run: Got filename: {filename} for {host}")
                    with open(filename, "w") as output_file:
                        output_file.write(connection.send_command(cmd))
            elif mode == OperatingModes.YeetMode:
                # Filename here is not derived from any user controlled source, no need to run it through the sanitizer
                filename = "configset.txt"
                log_q.put(f"debug run: Got filename: {filename} for {host}")
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
                log_q.put(f"warning Saved config for {host}")
            else:
                log_q.put(f"critical Unhandled Operating Mode: {mode = }")
                raise RuntimeError("Unhandled Operating Mode: {mode = }")
    except (NetmikoTimeoutException, NetmikoAuthenticationException) as err:
        log_q.put(
            f"critical Exception in netmiko connection: {type(err).__name__}: {err}"
        )
    except OSError as err:
        log_q.put(f"critical Error writing file: {type(err).__name__}: {err}")
    except Exception as err:
        log_q.put(f"critical Unknown exception: {type(err).__name__}: {err}")
    finally:
        os.chdir(original_directory)
    log_q.put(f"warning finished -  {host}")


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
    parser.add_argument(
        "-i", "--inventory", help="The inventory file to load.", required=True
    )
    parser.add_argument(
        "-j",
        "--jobfile",
        help="The file containing commands to send to the NOS",
        required=("--save-only" not in argv),
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
    """The entry point for interactive use (the only supported use as of now)
    1) Collect command line arguments
    2) Configure itself from parsed command line args
    3) Read configuration files given
    4) Creates output directories
    5) Create and start process pool
    6) Spinlock until process pool completes or Ctrl-C is received
    7) Cleanup and exit.
    """
    start = dtime.datetime.now()
    args = handle_arguments()
    log_level = logging.WARNING
    if args.quiet:
        log_level = logging.CRITICAL
    if args.verbose:
        log_level = logging.DEBUG
    # Regular multiprocessing.Queue's seem to not work (can't remember why, need to re-test)
    # Building Queue "Proxies" with multiprocessing.Manager seems to work great however.
    # Having the manager object around was useful in the past, but now it's not used again
    # manager = mp.Manager()
    #
    # Logging is done over a queue on a separate process to serialize everything
    # This is needed (from testing) because having large process pools fight over the same stdout did not go well.
    # It also uncouples tty/stdout performance from the execution of the worker processes.
    # This is useful because some terminals (really just Microsoft) are really slow.
    log_q = mp.Manager().Queue()
    logging_process = mp.Process(target=mctlogger.helper, args=(log_q, log_level))
    logging_process.start()
    log_q.put("warning Copyright Andrew Piroli 2019-2020")
    log_q.put("warning MIT License")
    log_q.put("warning ")
    if args.yeet:
        selected_mode = OperatingModes.YeetMode
    elif args.yoink:
        selected_mode = OperatingModes.YoinkMode
    elif args.save_only:
        selected_mode = OperatingModes.SaveOnlyMode
    else:
        log_q.put("critical No operating mode selected from command line args")
        raise RuntimeError("No operating mode selected from command line args")
    log_q.put(f"warning Running in operating mode: {selected_mode}")
    # This is a bit annoying to do, argparse can do validation (future self, you want to subclass `argparse.Action` override __call__)
    # Not sure it's worth it just yet, I'd even be fine crashing with invalid input especially since I *only* verify this one
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
    if args.jobfile:
        args.jobfile = abspath(args.jobfile)
    set_dir("Output", log_q)
    set_dir(dtime.datetime.now().strftime("%Y-%m-%d %H.%M"), log_q)
    netmiko_debug_file = abspath(".") / "netmiko." if args.debug_netmiko else None
    preloaded_jobfile = (
        preload_jobfile(args.jobfile, log_q) if not args.no_preload else None
    )
    p_config = {
        "mode": selected_mode,
        "log_queue": log_q,
        "netmiko_debug": netmiko_debug_file,
        "jobfile": args.jobfile,
        "jobfile_cache": preloaded_jobfile,
    }
    # Stackoverflow https://stackoverflow.com/a/63495323
    # CC-BY-SA 4.0
    # By: geitda https://stackoverflow.com/users/14133684/geitda
    # Hopefully this improves Ctrl-C performance....
    with ProcessPoolExecutor(max_workers=NUM_THREADS) as ex:
        # Can't `ex.map` here because of p_config
        # I could use itertools.repeat or whatever
        # I don't think it impacts performance much however
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
    os.chdir("..")  # Back out of timestamped folder
    os.chdir("..")  # Backout of "Output" folder
    # We are back where we started
    end = dtime.datetime.now()
    elapsed = (end - start).total_seconds()
    log_q.put(f"warning Time Elapsed: {elapsed}")
    # We could safely kill the logger because it's a process not a thread
    # (we could kill it even as a thread too since the program is about to be over lul)
    # But if stdout is very far behind it could lose some messages
    # So just do it the right way and let it shut itself down.
    log_q.put(THREAD_KILL_MSG)
    logging_process.join()


if __name__ == "__main__":
    main()
