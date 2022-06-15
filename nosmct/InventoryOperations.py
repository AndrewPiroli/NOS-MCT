import csv
import json
import pathlib
import requests
from multiprocessing import Queue
from typing import Iterator
from constants import LIBRENMS_API_BASE_URL


def read_csv_config(filename: pathlib.Path, log_q: Queue) -> Iterator[dict]:
    """
    Generator function to processes the CSV config file. Handles the various CSV formats and stitches the header onto each entry.
    """
    with open(filename, "r") as config_file:
        log_q.put(f"debug read_config: filename: {filename}")
        try:
            contents = [
                next(config_file) for _ in range(2)
            ]  # Reading 2 lines of the CSV, is sufficient to detect style
        except StopIteration:  # Only occurs when the file has less than two lines....not a very useful file, but I'm ready for it
            pass
        finally:
            full_contents = "".join(contents)
            config_file.seek(0)
        dialect = csv.Sniffer().sniff(full_contents)  # Detect CSV style
        del contents, full_contents
        reader = csv.reader(config_file, dialect)
        header = next(reader)
        log_q.put(f"debug read_config: header: {header}")
        for config_entry in reader:
            yield dict(zip(header, config_entry))


def lnms_config_validate_and_set_defaults(config: dict) -> bool:
    """
    Validate and fill in missing defaults for the loaded LibreNMS config
    """
    if not isinstance(config, dict):
        return False
    if "host" not in config:
        return False
    if "protocol" not in config:
        config["protocol"] = "https"
    if (not isinstance(config["protocol"], str)) or config["protocol"].lower() not in (
        "http",
        "https",
    ):
        return False
    else:
        config["protocol"] = config["protocol"].lower()
    if "port" not in config:
        config["port"] = 80 if config["protocol"] == "http" else 443
    if "tls_verify" not in config:
        config["tls_verify"] = config["protocol"] == "https"
    elif not isinstance(config["tls_verify"], bool):
        return False
    if "api_key" not in config:
        return False
    if not isinstance(config["api_key"], str):
        return False
    return True


def lnms_query(config: dict) -> dict:
    protocol = config["protocol"]
    host = config["host"]
    tls_verify = config["tls_verify"]
    headers = {"X-Auth-Token": config["api_key"]}
    response = requests.get(
        f"{protocol}://{host}{LIBRENMS_API_BASE_URL}devices",
        headers=headers,
        verify=tls_verify,
    ).json()
    return response


def validate_lnms_response(response: dict) -> bool:
    if not isinstance(response, dict):
        return False
    if "status" not in response or response["status"] != "ok":
        return False
    if "devices" not in response or not isinstance(response["devices"], list):
        return False
    return True


def get_inventory_from_lnms(filename: pathlib.Path, log_q: Queue):
    """
    Retrieve an inventory from LibreNMS
    The file passed is a json configuration file describing necessary info such as
     - protocol
     - host
     - port
     - API key
     - filters to apply to the data
     - transformations to apply to the data
    """
    with open(filename, "r") as config_file:
        confdata = json.load(config_file)
    if not lnms_config_validate_and_set_defaults(confdata):
        raise RuntimeError
    response = lnms_query(confdata)
    if not validate_lnms_response(response):
        raise RuntimeError
    print(response)
    raise RuntimeError
