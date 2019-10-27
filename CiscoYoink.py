# Andrew Piroli (c)2019
#  MIT LICENSE  #
from netmiko import ConnectHandler
import os
from concurrent.futures import ProcessPoolExecutor
import datetime as time
import shutil
from threading import Thread
from SimpleConfigParse import SimpleConfigParse
import multiprocessing as mp


class CiscoYoink(Thread):
    host, username, password, shared_list = None, None, None, None
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
    ]

    def __init__(self, host, username, password, shared_list):
        super().__init__()
        self.host = host
        self.username = username
        self.password = password
        self.shared_list = shared_list
        print(f"Yoinker: started host {self.host}")

    def run(self):
        with ConnectHandler(
            device_type="cisco_ios",
            host=self.host,
            username=self.username,
            password=self.password,
        ) as connection:
            hostname = connection.find_prompt().split("#")[0]
            for show in self.shows:
                show_f = show.replace(" ", "_")
                filename = f"{hostname}_{show_f}.txt"
                try:
                    with open(filename, "w") as show_file:
                        show_file.write(connection.send_command(show))
                        self.shared_list.append(
                            f"{hostname} {filename} epic_and_cool\n"
                        )
                except Exception as e:
                    print(f"Error writing show for {hostname}!")
                    print(e)
        print(f"Yoinker: finished host {self.host}")


class CiscoYoinkHelper:
    self_help_book = []
    filename = None

    def __init__(self, file="ciscoyoink_helper.log"):
        self.filename = file
        librarian = SimpleConfigParse(file)
        self.self_help_book = librarian.read()

    @staticmethod
    def set_dir(name):
        try:
            os.mkdir(name)
        except FileExistsError:
            pass
        except Exception as e:
            print(f"Could not create {name} directory in {os.getcwd()}\nReason {e}")
        try:
            os.chdir(name)
        except Exception as e:
            print(
                f"Could not change to {name} directory from {os.getcwd()}\nReason {e}"
            )

    def organize(self):
        original_dir = os.getcwd()
        for chapter in self.self_help_book:
            try:
                destination = chapter[1].replace(chapter[0] + "_", "")
                self.set_dir(chapter[0])
                shutil.move(f"../{chapter[1]}", f"./{destination}")
            except Exception as e:
                print(f"Error organizing {chapter[1]}: {e}")
                continue
            finally:
                os.chdir(original_dir)
        try:
            os.remove(self.filename)
        except:
            print("Could not remove log file")


def __thread_pool_wrapper(info):
    x = CiscoYoink(info[0], info[1], info[2], info[3])
    x.start()
    x.join()


if __name__ == "__main__":
    start = time.datetime.now()
    NUM_THREADS_MAX = 10
    config = SimpleConfigParse("sample.config").read()
    CiscoYoinkHelper.set_dir("Output")
    CiscoYoinkHelper.set_dir(time.datetime.now().strftime("%Y-%m-%d"))
    shared_list = mp.Manager().list()
    for index, c in enumerate(config):
        c.append(shared_list)
        config[index] = c
    with ProcessPoolExecutor(max_workers=NUM_THREADS_MAX) as ex:
        ex.map(__thread_pool_wrapper, config)
    try:
        with open("ciscoyoink_helper.log", "w+") as log:
            for record in shared_list:
                log.write(record)
    except Exception as e:
        print(f"Error: {e} in writing log file, shows may appear unsorted")
    CiscoYoinkHelper().organize()
    os.chdir("..")
    os.chdir("..")
    end = time.datetime.now()
    elapsed = (end - start).total_seconds()
    print(f"Time Elapsed: {elapsed}")
