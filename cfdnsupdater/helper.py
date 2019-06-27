import logging
from abc import ABC


class Loggable(ABC):
    _log: logging.Logger = None

    @classmethod
    def log(cls) -> logging.Logger:
        if cls._log is None:
            cls._log = logging.getLogger(cls.__name__)
            cls._log.setLevel(logging.DEBUG)
        return cls._log
