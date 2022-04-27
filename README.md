# Network Operating System Mass Configuration Tool [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![CodeFactor](https://www.codefactor.io/repository/github/andrewpiroli/nos-mct/badge)](https://www.codefactor.io/repository/github/andrewpiroli/nos-mct)

Pulls or pushes configs and shows/statistics from network devices.

Designed for minimal configuration, few dependencies, and fast deployment either as a one off or with cron/Task Scheduler.


## Requires:

* Python 3.6+
* Netmiko - Install via pip: `python3 -m pip install netmiko`


## Configuration:

A device inventory is passed with -i/--inventory

The inventory file is in CSV format with a header and 5 fields, hostname or ip, username, password, secret, device_type

The device_type field must match a netmiko device_type

Select operating mode with --yeet/--yoink and provide a jobfile with -j/--jobfile.
A "save only" operating mode is offered for convenience with the --save-only option, this mode just saves the config and does not require a jobfile.

The jobfile is a simple text file with commands in it.

In Yoink mode, the commands are run one by one in exec mode (for Cisco, other NOS will use their equivalent) and the output is saved per command.
In Yeet mode, the commands are sent all at once as a config set to be ran sequentially in config mode (or other NOS equivalent), a log of the commands run and any output is saved.

A list of supported device types can be found [here](./PLATFORMS.md)

## Example Usage:

Retrive configuration and status: ```python3 nosmct/nosmct.py -i examples/sample-inventory.csv -j examples/cisco-yoink-example.txt --yoink```

Deploy configuration: ```python3 nosmct/nosmct.py -i examples/sample-inventory.csv -j examples/cisco-yeet-example.txt --yeet```

Save configuration only: ```python3 nosmct/nosmct.py -i examples/sample-inventory.csv --save-only```

## Additional options

Increase number of concurrent connections by adding the `-t` or `--threads` flag followed by a number. (default is 10)

Pass `-q` or `--quiet` to supress most output.

Debug options: pass `--verbose` or `-v` for increased logging. `--debug-netmiko` for even more logging (this is done per thread and sent to a log file in the output folder), and `--no-preload` to disable caching of the configuration files.
