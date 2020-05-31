import logging
from multiprocessing.managers import BaseProxy
from queue import Empty as QEmptyException


class cylogger:
    def __init__(self, incoming_q: BaseProxy, config: dict):
        self.incoming_q = incoming_q
        self.config = config
        self.killed_flag = self.config["kill_callback"]
        self.output_level = self.config["output_level"]
        logging.basicConfig(format="", level=logging.CRITICAL)
        self.logger = logging.getLogger("cylogger")
        self.logger.setLevel(self.output_level)
        self.logger.debug("Logger: Initialized")

    def runloop(self):
        self.logger.debug("Logger: runloop() started")
        while not self.killed_flag():
            try:
                message = self.incoming_q.get(block=True, timeout=1)
            except QEmptyException:
                continue
            message_list = message.split(" ", 1)
            if hasattr(self.logger, message_list[0]):
                getattr(self.logger, message_list[0])(message_list[1])  # I'm sorry
            else:
                self.logger.critical(
                    "Logger: invalid message format recieved: {message}"
                )
        self.logger.debug("Closing logger thread!")
