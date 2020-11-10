# Network Operating System Mass Configuration Tool [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![CodeFactor](https://www.codefactor.io/repository/github/andrewpiroli/nos-mct/badge)](https://www.codefactor.io/repository/github/andrewpiroli/nos-mct)

Pulls or pushes configs and shows/statistics from network devices.

Designed for minimal configuration, few dependencies, and fast deployment either as a one off or with cron/Task Scheduler.


## Requires:

* Python 3.6+
* Netmiko


## Configuration:

A device inventory is passed with -i/--inventory

The inventory file is in CSV format with a header and 5 fields, hostname or ip, username, password, secret, device_type

The device_type field must match a netmiko device_type

Select operating mode with --yeet/--yoink and provide a jobfile with -j/--jobfile

The jobfile is a simple text file with commands in it.

In Yoink mode, the commands are run one by one in exec mode (for Cisco, other NOS will use their equivalent) and the output is saved per command.
In Yeet mode, the commands are sent all at once as a config set to be ran sequentially in config mode (or other NOS equivalent), a log of the commands run and any output is saved.

A list of supported device types can be found [here](./PLATFORMS.md)
