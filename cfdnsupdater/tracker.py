import socket
from abc import abstractmethod, ABCMeta
from ipaddress import IPv4Address, IPv6Address, ip_address
from threading import Event, Thread
from typing import Callable, Optional, Union, List

from pyroute2 import IPRoute
from pyroute2.netlink import nlmsg
from requests import get

from cfdnsupdater.helper import Loggable


class IPAddressTracker(Loggable, metaclass=ABCMeta):
    __slots__ = "_callback"

    def __init__(self):
        super(IPAddressTracker, self).__init__()
        self._callback = lambda x: None  # type: Callable[[Union[IPv4Address, IPv6Address]], None]

    def register_callback(self, callback):
        # type: (Callable[[Union[IPv4Address, IPv6Address]], None]) -> None
        self._callback = callback

    @abstractmethod
    def get_current(self):
        # type: () -> Optional[Union[IPv4Address, IPv6Address]]
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

    __slots = (
        "_iface_name", "_ipv6", "_family", "_ipdb", "_ipr", "_callback_uuid", "_kill_thread", "_t", "_iface_index")

    def __init__(self, ipv6, iface_name=None):
        # type: (bool, str) -> None
        super(NetlinkIPAddressTracker, self).__init__()
        self._iface_name = iface_name  # type: str
        self._ipv6 = ipv6  # type: bool
        self._family = socket.AF_INET6 if ipv6 else socket.AF_INET

        self._ipr = IPRoute()  # type: IPRoute
        self._callback_uuid = 0  # type: int

        self._kill_thread = Event()  # type: Event
        self._t = None  # type: Optional[Thread]

        self._iface_index = self._find_interface_index()  # type: int

    def _find_interface_index(self):
        # type: () -> int
        if self._iface_name is None:
            routes = self._ipr.get_default_routes(family=self._family)
            if len(routes) == 0:
                raise Exception("No interface name given and no default route set")
            interface = self._ipr.get_links(routes[0].get_attr('RTA_OIF'))[0]
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
        self._ipr.bind(async_cache=True)

        self._t = Thread(target=self._run, name="NetlinkIPAddressTracker")
        self._t.start()

        self.log().debug("Started")

    def get_current(self):
        # type: () -> Optional[Union[IPv4Address, IPv6Address]]
        nl_msgs = self._ipr.get_addr(family=self._family, index=self._iface_index,
                                     scope=NetlinkIPAddressTracker.SCOPE_GLOBAL)  # type: List[nlmsg]
        for nl_msg in nl_msgs:
            addr = ip_address(
                NetlinkIPAddressTracker._get_attr(nl_msg, 'IFA_ADDRESS'))  # type: Union[IPv4Address, IPv6Address]
            if addr.is_global:
                return addr
        return None

    def stop(self):
        self._kill_thread.set()
        self._ipr.close()
        if self._t is not None:
            self._t.join()
        self.log().debug("Stopped")

    @staticmethod
    def _get_attr(netlink_msg, attr_name):
        # type: (nlmsg, str) -> str
        """Get an attribute from a PyRoute2 object"""
        rule_attrs = netlink_msg.get('attrs', [])
        for attr in (attr for attr in rule_attrs if attr[0] == attr_name):
            return attr[1]

    def _run(self):
        while not self._kill_thread.is_set():
            for msg in self._ipr.get():
                if msg['event'] == NetlinkIPAddressTracker.ACTION_NEWADDR and msg['family'] == self._family \
                        and msg['scope'] == NetlinkIPAddressTracker.SCOPE_GLOBAL and msg['index'] == self._iface_index:
                    addr = ip_address(
                        NetlinkIPAddressTracker._get_attr(msg, 'IFA_ADDRESS'))  # type: Union[IPv4Address, IPv6Address]
                    if addr.is_global:
                        self._callback(addr)


class IntervalIPAddressTracker(IPAddressTracker, metaclass=ABCMeta):
    __slots__ = ("update_interval", "_kill_thread", "_t")

    def __init__(self, update_interval):
        # type: (int) -> None
        super(IntervalIPAddressTracker, self).__init__()
        self.update_interval = update_interval  # type: int

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
        while not self._kill_thread.wait(self.update_interval):
            addr = self.get_current()
            if addr is not None:
                self._callback(addr)


class IpifyIPAddressTracker(IntervalIPAddressTracker):
    __slots__ = "_ipv6"

    def __init__(self, ipv6, update_interval):
        # type: (bool, int) -> None
        super(IpifyIPAddressTracker, self).__init__(update_interval)
        self._ipv6 = ipv6  # type: bool

    def get_current(self):
        # type: () -> Optional[Union[IPv4Address, IPv6Address]]
        if self._ipv6:
            return IPv6Address(get('https://api6.ipify.org').text)
        else:
            return IPv4Address(get('https://api.ipify.org').text)


class SocketIPAddressTracker(IntervalIPAddressTracker):
    __slots__ = "_ipv6"

    def __init__(self, ipv6, update_interval):
        # type: (bool, int) -> None
        super(SocketIPAddressTracker, self).__init__(update_interval)
        self._ipv6 = ipv6  # type: bool

    def get_current(self):
        # type: () -> Optional[Union[IPv4Address, IPv6Address]]
        with socket.socket(socket.AF_INET6 if self._ipv6 else socket.AF_INET, socket.SOCK_DGRAM) as s:
            if self._ipv6:
                # Use Cloudflare DNS server to determine IPv6
                s.connect(("2606:4700:4700::1111", 80))
                return IPv6Address(s.getsockname()[0])
            else:
                # Use Cloudflare DNS server to determine IPv4
                s.connect(("1.1.1.1", 80))
                return IPv4Address(s.getsockname()[0])


class Monitor(Loggable):
    __slots__ = ("_tracker_factory", "_callback", "_autorestart_timeout", "_tracker", "_restart_thread", "_kill_thread",
                 "_is_running", "_last_ip")

    def __init__(self, tracker_factory, callback, autorestart_timeout):
        # type: (Callable[[], IPAddressTracker], Callable[[Union[IPv4Address, IPv6Address]], None], int) -> None
        super(Monitor, self).__init__()
        self._tracker_factory = tracker_factory  # type: Callable[[], IPAddressTracker]
        self._callback = callback  # type: Optional[Callable[[Union[IPv4Address, IPv6Address]], None]]
        self._autorestart_timeout = autorestart_timeout  # type: int

        self._tracker = None  # type: Optional[IPAddressTracker]
        self._restart_thread = None  # type: Optional[Thread]
        self._kill_thread = Event()  # type: Event
        self._is_running = False  # type: bool
        self._last_ip = None  # type: Optional[Union[IPv4Address, IPv6Address]]

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
        # type: (Union[IPv4Address, IPv6Address]) -> None
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
            # initial run
            current_ip = self._tracker.get_current()
            if current_ip is None:
                self.log().error("Couldn't find a valid external IP address!")
            else:
                self._ip_updated(current_ip)
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
