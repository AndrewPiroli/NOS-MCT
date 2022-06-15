from enum import Enum, auto

NUM_THREADS_DEFAULT = (
    10  # Process pool default size, can be overridden with the --threads option
)

THREAD_KILL_MSG = "NOSMCT-STOP-THREAD"  # Sent to threads/processes so they know to shut themselves down


class OperatingModes(Enum):
    YeetMode = auto()  # We are sending configurations to the devices
    YoinkMode = auto()  # We are pulling configurations/status from the devices
    SaveOnlyMode = auto()  # We are just saving the config


LIBRENMS_API_VER = "v0"
LIBRENMS_API_BASE_URL = f"/api/{LIBRENMS_API_VER}/"
