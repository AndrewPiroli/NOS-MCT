# Cisco-Config-Yoinker [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

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
* show spanning-tree
* show spanning-tree detail
* show cdp neighbor
* show cdp neighbor detail
* show lldp neighbor
* show lldp neighbor detail
* show interfaces
* show ip interface brief
* show ipv6 interface brief
* show ip route
* show ip mroute
* show ipv6 route
* show ipv6 mroute
* show ip protocols
* show ipv6 protocols

## Requires:

* Python 3.6+
* Netmiko


## Configuration:

By defualt, configuration is loaded from "Cisco-Yoink-Default.config" in the same directory as the script.

A different config can be loaded through the --config or -c command line option.

The config file is in CSV format with a header and 4 fields, hostname or ip, username, password, secret
