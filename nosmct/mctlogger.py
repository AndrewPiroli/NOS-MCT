import logging
from multiprocessing.managers import BaseProxy
from queue import Empty as QEmptyException
from constants import (
    THREAD_KILL_MSG,
)


class mctlogger:
    def __init__(self, incoming_q: BaseProxy, output_level: int):
        self.incoming_q = incoming_q
        self.output_level = output_level
        logging.basicConfig(format="", level=logging.CRITICAL)
        self.logger = logging.getLogger("nosmct")
        self.logger.setLevel(self.output_level)
        self.logger.debug("Logger: Initialized")

    def runloop(self):
        self.logger.debug("Logger: runloop() started")
        while True:
            try:
                message = self.incoming_q.get(block=True, timeout=1)
                message_list = message.split(" ", 1)
                if hasattr(self.logger, message_list[0]):
                    getattr(self.logger, message_list[0])(message_list[1])  # I'm sorry
                elif message == THREAD_KILL_MSG:
                    break
                else:
                    self.logger.critical(
                        f"Logger: invalid message format recieved: {message}"
                    )
            except (KeyboardInterrupt, QEmptyException):
                pass
        self.logger.debug("Closing logger!")


def helper(incoming_q: BaseProxy, output_level: int):
    mctlogger(incoming_q, output_level).runloop()
