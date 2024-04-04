# SPDX-License-Identifier: MIT
# Author: Andrew Piroli
# Year: 2022
import csv
import json
import pathlib
import re
import logging
from typing import Iterator, List, Literal, Optional, Union
from dataclasses import dataclass
from constants import LIBRENMS_API_BASE_URL

try:
    import requests

    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False


@dataclass(repr=True, order=True)
class FilterEntry:
    field: str
    qualifier: Union[Literal["EQ"], Literal["LIKE"]]
    qualifiees: Union[str, List[str]]
    inverted: bool
    must_match_all: bool

    def ismatch(self, x: dict) -> bool:
        if self.field not in x:
            raise RuntimeError("Undefined behavior")
        to_match = str(x[self.field])
        if not isinstance(self.qualifiees, list):
            self.qualifiees = [
                self.qualifiees,
            ]
        matches = 0
        for candidate in self.qualifiees:
            if self.qualifier == "EQ":
                matches += 1 if to_match == str(candidate) else 0
            elif self.qualifier == "LIKE":
                matches += 1 if re.search(str(candidate), to_match) else 0
            else:
                raise RuntimeError("unreachable FilterQualifer")
        if self.must_match_all:
            return (len(self.qualifiees) == matches) != self.inverted
        else:
            return (matches > 0) != self.inverted


BAD_OS = [
    r"windows",
    r"linux",
    r"proxmox",
    r"vmware",
    r"esxi",
    r"apc",
    r"drac",
    r"ping",
    r"pdu",
    r"exagrid",
    r"\\s",
    r"^$",
]
DEFAULT_FILTER = FilterEntry("os", "LIKE", BAD_OS, inverted=True, must_match_all=False)


def read_csv_config(filename: pathlib.Path) -> Iterator[dict]:
    """
    Generator function to processes the CSV config file. Handles the various CSV formats and stitches the header onto each entry.
    """
    logger = logging.getLogger("nosmct")
    with open(filename, "r") as config_file:
        logger.debug(f"read_config: filename: {filename}")
        try:
            contents = [
                next(config_file) for _ in range(2)
            ]  # Reading 2 lines of the CSV, is sufficient to detect style
        except (
            StopIteration
        ):  # Only occurs when the file has less than two lines....not a very useful file, but I'm ready for it
            pass
        finally:
            full_contents = "".join(contents)
            config_file.seek(0)
        dialect = csv.Sniffer().sniff(full_contents)  # Detect CSV style
        del contents, full_contents
        reader = csv.reader(config_file, dialect)
        header = next(reader)
        logger.debug(f"read_config: header: {header}")
        for config_entry in reader:
            yield dict(zip(header, config_entry))


# Check if a key exists
lnms_config_exists = lambda key, config: (key in config)
# Set a key to some default value if it doesn't exist
lnms_config_default = (
    lambda key, default, config: config.__setitem__(key, default) if key not in config else None
)
# Check a key exists and it's value against a list of valid options
lnms_config_require = lambda key, valid_options, config: (key in config and config[key] in valid_options)


def lnms_config_validate_and_set_defaults(config: dict) -> bool:
    """
    Validate and fill in missing defaults for the loaded LibreNMS config
    """
    logger = logging.getLogger("nosmct")
    if not isinstance(config, dict):
        logger.critical("Error: LibreNMS config malformed (not dict)")
        return False
    for required_key in ("host", "api_key", "filters", "username", "password"):
        if not lnms_config_exists(required_key, config):
            logger.critical(f"Required config key: {required_key} not found in LibreNMS config")
            return False
    lnms_config_default("protocol", "https", config)
    if not lnms_config_require("protocol", ("http", "https"), config):
        logger.critical("LibreNMS config invalid protocol: " + config["protocol"])
        return False
    if not lnms_config_exists("port", config):
        config["port"] = 80 if config["protocol"] == "http" else 443
    elif not isinstance(config["port"], int):
        config["port"] = int(config["port"])
    if not lnms_config_require("port", range(65536), config):
        logger.critical("Invalid port no: " + config["port"])
        return False
    if not lnms_config_exists("tls_verify", config):
        lnms_config_default("tls_verify", (config["protocol"] == "https"), config)
    elif not lnms_config_require("tls_verify", (True, False), config):
        logger.critical("LibreNMS config key tls_verify must be true or false")
        return False
    if not isinstance(config["api_key"], str):
        logger.critical("LibreNMS config key api_key must be a string")
        return False
    lnms_config_default("filters", [], config)
    if not isinstance(config["filters"], list):
        logger.critical("LibreNMS config 'filters' must be a list")
        return False
    lnms_config_default("secret", config["password"], config)
    return True


def lnms_query(config: dict, endpoint: str) -> Optional[dict]:
    """
    Perform a LibreNMS GET request and return the JSON response
    """
    if not HAVE_REQUESTS:
        return None
    protocol = config["protocol"]
    host = config["host"]
    tls_verify = config["tls_verify"]
    headers = {"X-Auth-Token": config["api_key"]}
    port = ":" + str(config["port"])
    response = requests.get(
        f"{protocol}://{host}{port}{LIBRENMS_API_BASE_URL}{endpoint}",
        headers=headers,
        verify=tls_verify,
    ).json()
    return response


def validate_lnms_response(response: dict) -> bool:
    """
    Run basic checks on the response data from LibreNMS
    """
    logger = logging.getLogger("nosmct")
    if not isinstance(response, dict):
        logger.critical("Invalid response from LibreNMS API")
        return False
    if "status" not in response or response["status"] != "ok":
        logger.critical("LibreNMS API returned a non-ok status")
        return False
    if "devices" not in response or not isinstance(response["devices"], list):
        logger.critical("LibreNMS API didn't return any devices")
        return False
    return True


def lnms_run_filter(devices: list, filter: FilterEntry) -> List[dict]:
    """
    Run a single FilterEntry on the device list data
    """
    passed = list()
    for device in devices:
        if not isinstance(device, dict):
            continue
        if filter.ismatch(device):
            passed.append(device)
    return passed


def lnms_parse_filters(filterconfig: List[dict]) -> List[FilterEntry]:
    """
    Parse the list of filters from JSON/dict to FilterEntry objects
    """
    filters = []
    if not isinstance(filterconfig, list):
        return filters
    for potential_filter in filterconfig:
        parsed_filter = FilterEntry(**potential_filter)
        if isinstance(parsed_filter, FilterEntry):
            filters.append(parsed_filter)
    return filters


lnms_to_netmiko_lut = {"ios": "cisco_ios", "iosxe": "cisco_ios"}


def get_inventory_from_lnms(filename: pathlib.Path) -> Optional[Iterator[dict]]:
    """
    Retrieve an inventory from LibreNMS
    The file passed is a json configuration file describing necessary info such as
     - protocol
     - host
     - port
     - API key
     - filters to apply to the data
     - network device login data
    """
    logger = logging.getLogger("nosmct")
    if not HAVE_REQUESTS:
        logger.critical(
            "requests library not installed. Please install it via pip to support LibreNMS integration"
        )
        return None
    with open(filename, "r") as config_file:
        confdata = json.load(config_file)
    if not lnms_config_validate_and_set_defaults(confdata):
        logger.critical("LibreNMS config validation failed")
        return None
    response = lnms_query(confdata, "devices")
    if not validate_lnms_response(response):
        logger.critical("LibreNMS response validation failed")
        return None
    parsed_filters = lnms_parse_filters(confdata["filters"])
    devices = lnms_run_filter(response["devices"], DEFAULT_FILTER)
    for a_filter in parsed_filters:
        devices = lnms_run_filter(devices, a_filter)
    for dev in devices:
        conn_addr = None
        if len(dev["ip"].strip()):
            conn_addr = dev["ip"]
        elif len(dev["hostname"].strip()):
            conn_addr = dev["hostname"]
        elif len(dev["sysName"].strip()):
            conn_addr = dev["sysName"]
        if not conn_addr:
            continue
        if dev["os"] in lnms_to_netmiko_lut:
            netmiko_os = lnms_to_netmiko_lut[dev["os"]]
        else:
            continue
        yield {
            "host": conn_addr,
            "username": confdata["username"],
            "password": confdata["password"],
            "secret": confdata["secret"],
            "device_type": netmiko_os,
        }
