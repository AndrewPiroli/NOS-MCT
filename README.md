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
