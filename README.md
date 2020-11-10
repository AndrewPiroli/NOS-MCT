# Network Operating System Mass Configuration Tool [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![CodeFactor](https://www.codefactor.io/repository/github/andrewpiroli/nos-mct/badge)](https://www.codefactor.io/repository/github/andrewpiroli/nos-mct)

Pulls or pushes configs and shows/statistics from network devices.

Designed for minimal configuration, few dependencies, and fast deployment either as a one off or with cron/Task Scheduler.


## Requires:

* Python 3.6+
* Netmiko


## Configuration:

By defualt, configuration is loaded from "nosmct.default.config" in the same directory as the script.

A different config can be loaded through the --config or -c command line option.

The config file is in CSV format with a header and 5 fields, hostname or ip, username, password, secret, device_type

The device_type field must match a netmiko device_type

Commands must be provided in a file in the shows directory with the naming convention of "shows_{device_type}.txt" A sample for the cisco_ios and cisco_ios_telnet are provided.

A list of supported device types can be found [here](./PLATFORMS.md)
