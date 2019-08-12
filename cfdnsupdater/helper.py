import logging
from abc import ABCMeta
from typing import Optional

import six


@six.add_metaclass(ABCMeta)
class Loggable(object):
    __slots__ = ()
    _log = None  # type: Optional[logging.Logger]

    @classmethod
    def log(cls):
        # type: () -> logging.Logger
        if cls._log is None:
            cls._log = logging.getLogger(cls.__name__)
            cls._log.setLevel(logging.DEBUG)
        return cls._log
