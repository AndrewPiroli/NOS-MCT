# Andrew Piroli (c)2019
#  MIT LICENSE  #
import datetime as time
import shutil
import multiprocessing as mp
import argparse
import csv
import os
from concurrent.futures import ProcessPoolExecutor
from netmiko import ConnectHandler

shows = [
    "show run",
    "show run all",
    "show vlan",
    "show vlan brief",
    "show vtp status",
    "show vtp password",
    "show start",
    "show int trunk",
    "show version",
    "show spanning-tree",
    "show spanning-tree detail",
    "show cdp neighbor",
    "show cdp neighbor detail",
    "show lldp neighbor",
    "show lldp neighbor detail",
    "show interfaces",
    "show ipv6 interface brief",
    "show ip route",
    "show ip mroute",
    "show ipv6 route",
    "show ip protocols",
    "show ipv6 protocols",
]


def run(info, shared_list):
    """
    Worker thread running in process
    Responsible for creating the connection to the device, finding the hostname, running the shows, and saving them to the current directory.
    Takes `info` list which contains the login information
    Takes `shared_list` which is a multiprocessing.Manager.List used to share python objects across processes - manages pickling/de-pickling for us
    """
    host = info[0]
    username = info[1]
    password = info[2]
    secret = info[3]
    print(f"running - {host} {username}")
    with ConnectHandler(
        device_type="cisco_ios",
        host=host,
        username=username,
        password=password,
        secret=secret,
    ) as connection:
        connection.enable()
        hostname = connection.find_prompt().split("#")[0]
        for show in shows:
            filename = show.replace(" ", "_")
            filename = f"{hostname}_{filename}.txt"
            try:
                with open(filename, "w") as show_file:
                    show_file.write(connection.send_command(show))
                    shared_list.append(f"{hostname} {filename}")
            except Exception as e:
                print(f"Error writing show for {hostname}!")
                print(e)
    print(f"Yoinker: finished host {host}")


def __set_dir(name):
    """
    Helper function to create (and handle existing) folders and change directory to them automatically.
    """
    try:
        os.mkdir(name)
    except FileExistsError:
        pass
    except Exception as e:
        print(f"Could not create {name} directory in {os.getcwd()}\nReason {e}")
    try:
        os.chdir(name)
    except Exception as e:
        print(f"Could not change to {name} directory from {os.getcwd()}\nReason {e}")


def __organize(lst):
    """
    Responsible for taking the list of filenames of shows, creating folders, and renaming the shows into the correct folder.

    Process:

    1) Takes a list of strings in the format of '{Hostname} {Filename}'
    2) For each element, split the string between the hostname and filename
    3) Create a folder (__set_dir) for the hostname
    4) The filename has an extra copy of the hostname, which is stripped off.
    5) Move+rename the file from the root dir into the the folder for the hostname
    """
    original_dir = os.getcwd()
    for chapter in lst:
        chapter = chapter.split(" ")
        try:
            destination = chapter[1].replace(chapter[0] + "_", "")
            __set_dir(chapter[0])
            shutil.move(f"../{chapter[1]}", f"./{destination}")
        except Exception as e:
            print(f"Error organizing {chapter[1]}: {e}")
            continue
        finally:
            os.chdir(original_dir)


if __name__ == "__main__":
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
        "-q", "--quiet", help="Suppress all output", action="store_true"
    )
    output_config.add_argument(
        "-v", "--verbose", help="Enable verbose output", action="store_true"
    )
    args = parser.parse_args()
    start = time.datetime.now()
    print("Copyright Andrew Piroli 2019")
    print("MIT License")
    print()
    if args.quiet or args.verbose:
        print("Quiet and Verbose options are not yet implemented!")
    NUM_THREADS_MAX = 10
    if args.threads:
        try:
            NUM_THREADS_MAX = int(args.threads)
            if NUM_THREADS_MAX > 25 or NUM_THREADS_MAX < 1:
                if args.force:
                    pass
                else:
                    print("NUM_THREADS out of range: setting to default value of 10")
                    NUM_THREADS_MAX = 10
        except:
            print("NUM_THREADS not recognized: setting to default value of 10")
            NUM_THREADS_MAX = 10
    if args.config:
        config = list(csv.reader(open(args.config)))
        del config[0]  # Skip the CSV header
    else:
        config = list(csv.reader(open("Cisco-Yoink-Default.config")))
        del config[0]  # Skip the CSV header
    __set_dir("Output")
    __set_dir(time.datetime.now().strftime("%Y-%m-%d %H.%M"))
    shared_list = mp.Manager().list()
    with ProcessPoolExecutor(max_workers=NUM_THREADS_MAX) as ex:
        for creds in config:
            ex.submit(run, creds, shared_list)
    __organize(list(shared_list))
    os.chdir("..")
    os.chdir("..")
    end = time.datetime.now()
    elapsed = (end - start).total_seconds()
    print(f"Time Elapsed: {elapsed}")
