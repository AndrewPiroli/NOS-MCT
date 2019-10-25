# Cisco-Config-Yoinker

Pulls down configs from multiple Cisco switches(other Cisco devices will most likely work as well)

Designed for minimal configuration and fast deployment either as a one off or with cron/Task Scheduler.

### By default ConfigYoinker saves the following shows:

* show run
* show run all
* show vlan
* show vlan brief
* show vtp status
* show vtp password
* show start
* show int trunk
* show version

## Requires:

* Python 3.6+
* Netmiko


## Configuration:

By defualt, configuration is loaded from "sample.config" in the same directory as the script.

The config file is very simple, each line is an entry with 3 fields separated by a space.

The first field is the ip or hostname of the device, the second is the username to log into the device, the thrid is the password.

Enable passwords are not supported, the account must be configured to log in directly to privileged exec mode.
