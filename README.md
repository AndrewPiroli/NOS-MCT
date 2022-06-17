# Network Operating System Mass Configuration Tool [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![CodeFactor](https://www.codefactor.io/repository/github/andrewpiroli/nos-mct/badge)](https://www.codefactor.io/repository/github/andrewpiroli/nos-mct)

Pulls or pushes configs and shows/statistics from network devices.

Designed for minimal configuration, few dependencies, and fast deployment either as a one off or with cron/Task Scheduler.


## Requires:

* Python 3.6+
* Netmiko - Install via pip: `python3 -m pip install netmiko`
* Requests - Install via pip `python3 -m pip install requests`


## Configuration:

There are 2 options for specifiying what devices to target: manual CSV inventory or LibreNMS integration

### CSV 
A device inventory is passed with -i/--inventory

The inventory file is in CSV format with a header and 5 fields, hostname or ip, username, password, secret, device_type

The device_type field must match a netmiko device_type

### LibreNMS integration

A JSON config file is used to connect to LibreNMS. You will need API access and an API key, read only permissions are suffcient.

The JSON file MUST specify the following:
 - `host` String - hostname/ip of your LibreNMS instance
 - `api_key` String - LibreNMS API key
 - `username` String - network device login username (NOT LibreNMS)
 - `password` String - network device password

Optional configuration options:
 - `protocol` String - either "http" or "https" the protocol to connect to LibreNMS with (default: https)
 - `tls_verify` boolean - controls certificate validation if HTTPS is used (default: True if HTTPS is the protocol)
  - `secret` String - network device 'secret' (default: same as password)
  - filters List of Object (spec below) - filters to limit the data from LibreNMS

The `filters` section of the JSON file allows you to filter the response from LibreNMS to exclude certain devices. Filters section is a list of objects with a:
 -`field` (the part of the response that is filtered on)
 -`qualifier` either "EQ" or "LIKE" for exact match or regex match respectively
 - `qualifiees` either a single string or list of strings that the filter will check the field against
 - `inverted` boolean will invert the filter
 - `must_match_all` boolean will control wether the filter will stop on the first match or if all qualifiees must succeed.

 There is no limit to the number of filters. A default filter is built into the program to filter devices with OSes that are obviously not useful (Windows, Linux, Proxmox, Vmware, APC, etc)

### Configuration (cont.)

The examples directory has a sample of both CSV and LibreNMS config files

### Jobfiles

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
