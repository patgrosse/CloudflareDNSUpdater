import socket
from abc import abstractmethod, ABCMeta
from threading import Event, Thread
from typing import Callable, Optional

import six
from pyroute2 import IPDB, IPRoute
from pyroute2.netlink import nlmsg
from requests import get

from cfdnsupdater.helper import Loggable


@six.add_metaclass(ABCMeta)
class IPAddressTracker(Loggable):
    __slots__ = "_callback"

    def __init__(self):
        super(IPAddressTracker, self).__init__()
        self._callback = lambda x: None  # type: Callable[[str], None]

    def register_callback(self, callback):
        # type: (Callable[[str], None]) -> None
        self._callback = callback

    @abstractmethod
    def get_current(self):
        # type: () -> str
        raise NotImplementedError()

    @abstractmethod
    def start(self):
        raise NotImplementedError()

    @abstractmethod
    def stop(self):
        raise NotImplementedError()


class NetlinkIPAddressTracker(IPAddressTracker):
    SCOPE_GLOBAL = 0  # type: int
    ACTION_NEWADDR = "RTM_NEWADDR"  # type: str

    __slots = ("_iface_name", "_ipv6", "_family", "_ipdb", "_ipr", "_callback_uuid", "_iface_index")

    def __init__(self, ipv6, iface_name=None):
        # type: (bool, str) -> None
        super(NetlinkIPAddressTracker, self).__init__()
        self._iface_name = iface_name  # type: str
        self._ipv6 = ipv6  # type: bool
        self._family = socket.AF_INET6 if ipv6 else socket.AF_INET

        self._ipdb = IPDB()  # type: IPDB
        self._ipr = IPRoute()  # type: IPRoute
        self._callback_uuid = 0  # type: int

        self._iface_index = self._find_interface_index()  # type: int

    def _find_interface_index(self):
        # type: () -> int
        if self._iface_name is None:
            routes = self._ipdb.routes.filter({"dst": "default", "family": self._family})
            if len(routes) == 0:
                raise Exception("No interface name given and no default route set")
            interface = self._ipr.get_links(routes[0]["route"]["oif"])[0]
            ifname = interface.get_attr("IFLA_IFNAME")
            self.log().info("Using interface %s" % ifname)
            return interface.get("index")
        else:
            iface_ids = self._ipr.link_lookup(ifname=self._iface_name)
            if len(iface_ids) != 1:
                raise Exception(
                    "Found %d interfaces matching the interface name %s" % (len(iface_ids), self._iface_name))
            return iface_ids[0]

    def start(self):
        def new_address_callback(_ipdb, netlink_message, action):
            # type: (IPDB, nlmsg, str) -> None
            if action == self.ACTION_NEWADDR and netlink_message['family'] == self._family and \
                    netlink_message['scope'] == self.SCOPE_GLOBAL and netlink_message['index'] == self._iface_index:
                addr = NetlinkIPAddressTracker._get_attr(netlink_message, 'IFA_ADDRESS')
                self._callback(addr)

        self._callback_uuid = self._ipdb.register_callback(new_address_callback)
        self.log().debug("Started")

    def get_current(self):
        # type: () -> str
        nl_msg = self._ipr.get_addr(family=self._family, index=self._iface_index)
        return NetlinkIPAddressTracker._get_attr(nl_msg[0], 'IFA_ADDRESS')

    def stop(self):
        self._ipdb.unregister_callback(self._callback_uuid)
        self._ipdb.release()
        self._ipr.close()
        self.log().debug("Stopped")

    @staticmethod
    def _get_attr(netlink_msg, attr_name):
        # type: (nlmsg, str) -> str
        """Get an attribute from a PyRoute2 object"""
        rule_attrs = netlink_msg.get('attrs', [])
        for attr in (attr for attr in rule_attrs if attr[0] == attr_name):
            return attr[1]


@six.add_metaclass(ABCMeta)
class IntervalIPAddressTracker(IPAddressTracker):
    __slots__ = ("update_interval", "_kill_thread", "_t")

    def __init__(self, update_interval):
        """
        :type update_interval: int
        """
        super(IntervalIPAddressTracker, self).__init__()
        self.update_interval = update_interval

        self._kill_thread = Event()  # type: Event
        self._t = None  # type: Optional[Thread]

    def start(self):
        self._t = Thread(target=self._run, name="IntervalIPAddressTracker")
        self._t.start()
        self.log().debug("Started")

    def stop(self):
        self._kill_thread.set()
        if self._t is not None:
            self._t.join()
        self.log().debug("Stopped")

    def _run(self):
        # initial run
        self._callback(self.get_current())
        while not self._kill_thread.wait(self.update_interval):
            self._callback(self.get_current())


class IpifyIPAddressTracker(IntervalIPAddressTracker):
    __slots__ = "_ipv6"

    def __init__(self, ipv6, update_interval):
        # type: (bool, int) -> None
        super(IpifyIPAddressTracker, self).__init__(update_interval)
        self._ipv6 = ipv6  # type: bool

    def get_current(self):
        # type: () -> str
        if self._ipv6:
            ip = get('https://api6.ipify.org').text
        else:
            ip = get('https://api.ipify.org').text
        return ip


class SocketIPAddressTracker(IntervalIPAddressTracker):
    __slots__ = "_ipv6"

    def __init__(self, ipv6, update_interval):
        # type: (bool, int) -> None
        super(SocketIPAddressTracker, self).__init__(update_interval)
        self._ipv6 = ipv6  # type: bool

    def get_current(self):
        # type: () -> str
        if self._ipv6:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            # Use Cloudflare DNS server to determine IPv6
            s.connect(("2606:4700:4700::1111", 80))
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Use Cloudflare DNS server to determine IPv4
            s.connect(("1.1.1.1", 80))

        ip = s.getsockname()[0]
        s.close()
        return ip


class Monitor(Loggable):
    __slots__ = ("_tracker_factory", "_callback", "_autorestart_timeout", "_tracker", "_restart_thread", "_kill_thread",
                 "_is_running", "_last_ip")

    def __init__(self, tracker_factory, callback, autorestart_timeout):
        # type: (Callable[[], IPAddressTracker], Callable[[str], None], int) -> None
        super(Monitor, self).__init__()
        self._tracker_factory = tracker_factory  # type: Callable[[], IPAddressTracker]
        self._callback = callback  # type: Optional[Callable[[str], None]]
        self._autorestart_timeout = autorestart_timeout  # type: int

        self._tracker = None  # type: Optional[IPAddressTracker]
        self._restart_thread = None  # type: Optional[Thread]
        self._kill_thread = Event()  # type: Event
        self._is_running = False  # type: bool
        self._last_ip = None  # type: Optional[str]

    def start(self):
        self._restart_thread = Thread(target=self._run, name="MonitorRestart")
        self._restart_thread.setDaemon(True)
        self._restart_thread.start()
        self.log().debug("Started")

    def stop(self):
        self._kill_thread.set()
        if self._restart_thread is not None:
            self._restart_thread.join()
        self.log().debug("Stopped")

    def _ip_updated(self, ip):
        # type: (str) -> None
        if ip != self._last_ip:
            self._last_ip = ip
            if self._callback is not None:
                self._callback(ip)

    def _start_tracker(self):
        # noinspection PyBroadException
        try:
            self._tracker = self._tracker_factory()
            self._tracker.register_callback(self._ip_updated)
            self._tracker.start()
        except Exception:
            self.log().exception("Exception on starting tracker")

    def _stop_tracker(self):
        # noinspection PyBroadException
        try:
            if self._tracker is not None:
                self._tracker.stop()
        except Exception:
            self.log().exception("Exception on stopping tracker")

    def _run(self):
        self._start_tracker()
        while not self._kill_thread.wait(self._autorestart_timeout):
            self._stop_tracker()
            self.log().debug("Restarting tracker...")
            self._start_tracker()
        self._stop_tracker()
