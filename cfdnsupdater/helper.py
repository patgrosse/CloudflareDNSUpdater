import logging
from abc import ABCMeta

import six


@six.add_metaclass(ABCMeta)
class Loggable(object):
    _log = None  # type: logging.Logger

    @classmethod
    def log(cls):
        # type: () -> logging.Logger
        if cls._log is None:
            cls._log = logging.getLogger(cls.__name__)
            cls._log.setLevel(logging.DEBUG)
        return cls._log
