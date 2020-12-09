from enum import Enum, auto

NUM_THREADS_DEFAULT = (
    10  # Process pool default size, can be overridden with the --threads option
)

THREAD_KILL_MSG = "NOSMCT-STOP-THREAD"


class OperatingModes(Enum):
    YeetMode = auto()  # We are sending configurations to the devices
    YoinkMode = auto()  # We are pulling configurations/status from the devices
