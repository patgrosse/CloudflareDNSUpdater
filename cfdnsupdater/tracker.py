import logging
import socket
import time
from abc import abstractmethod, ABC
from socket import AddressFamily
from threading import Event, Thread
from typing import Callable, Union

from pyroute2 import IPDB, IPRoute
from requests import get

from cfdnsupdater.helper import Loggable


class IPAddressTracker(Loggable, ABC):
    _callback: Callable[[str], None]

    def __init__(self):
        super().__init__()
        self._callback = lambda x: None

    def register_callback(self, callback: Callable[[str], None]):
        self._callback = callback

    @abstractmethod
    def get_current(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def start(self):
        raise NotImplementedError()

    @abstractmethod
    def stop(self):
        raise NotImplementedError()


class NetlinkIPAddressTracker(IPAddressTracker):
    _iface_name: str
    _ipv6: bool
    _family: AddressFamily
    _iface_index: Union[int, None]
    _ipdb: IPDB
    _ipr: IPRoute
    _callback_uuid: int

    SCOPE_GLOBAL = 0
    ACTION_NEWADDR = 'RTM_NEWADDR'

    def __init__(self, ipv6: bool, iface_name: str = None):
        super().__init__()
        self._iface_name = iface_name
        self._ipv6 = ipv6
        self._family = socket.AF_INET6 if ipv6 else socket.AF_INET

        self._ipdb = IPDB()
        self._ipr = IPRoute()
        self._callback_uuid = 0

        self._iface_index = self._find_interface_index()

    def _find_interface_index(self):
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
        def new_address_callback(_ipdb: IPDB, netlink_message, action: str):
            if action == self.ACTION_NEWADDR and netlink_message['family'] == self._family and \
                    netlink_message['scope'] == self.SCOPE_GLOBAL and netlink_message['index'] == self._iface_index:
                addr = NetlinkIPAddressTracker._get_attr(netlink_message, 'IFA_ADDRESS')
                self._callback(addr)

        self._callback_uuid = self._ipdb.register_callback(new_address_callback)
        self.log().debug("Started")

    def get_current(self) -> str:
        nl_msg = self._ipr.get_addr(family=self._family, index=self._iface_index)
        return NetlinkIPAddressTracker._get_attr(nl_msg[0], 'IFA_ADDRESS')

    def stop(self):
        self._ipdb.unregister_callback(self._callback_uuid)
        self._ipdb.release()
        self._ipr.close()
        self.log().debug("Stopped")

    @staticmethod
    def _get_attr(pyroute2_obj, attr_name: str):
        """Get an attribute from a PyRoute2 object"""
        rule_attrs = pyroute2_obj.get('attrs', [])
        for attr in (attr for attr in rule_attrs if attr[0] == attr_name):
            return attr[1]


class IntervalIPAddressTracker(IPAddressTracker, ABC):
    _kill_thread: Event
    _t: Union[Thread, None]

    def __init__(self, update_interval: int):
        super().__init__()
        self.update_interval = update_interval

        self._kill_thread = Event()
        self._t = None

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
    _ipv6: bool

    def __init__(self, ipv6: bool, update_interval: int):
        super().__init__(update_interval)
        self._ipv6 = ipv6

    def get_current(self) -> str:
        if self._ipv6:
            ip = get('https://api6.ipify.org').text
        else:
            ip = get('https://api.ipify.org').text
        return ip


class SocketIPAddressTracker(IntervalIPAddressTracker):
    _ipv6: bool

    def __init__(self, ipv6: bool, update_interval: int):
        super().__init__(update_interval)
        self._ipv6 = ipv6

    def get_current(self) -> str:
        if self._ipv6:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            # Use CloudFlare DNS server to determine IPv6
            s.connect(("2606:4700:4700::1111", 80))
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Use CloudFlare DNS server to determine IPv4
            s.connect(("1.1.1.1", 80))

        ip = s.getsockname()[0]
        s.close()
        return ip


# noinspection PyBroadException
class Monitor(Loggable):
    _tracker_factory: Callable[[], IPAddressTracker]
    _tracker: Union[IPAddressTracker, None]
    _autorestart_timeout: int

    _restart_thread: Union[Thread, None]
    _kill_thread: Event
    _is_running: bool
    _callback: Union[Callable[[str], None], None]
    _last_ip: Union[str, None]

    def __init__(self, tracker_factory: Callable[[], IPAddressTracker], callback: Callable[[str], None],
                 autorestart_timeout: int):
        super().__init__()
        self._tracker_factory = tracker_factory
        self._callback = callback
        self._autorestart_timeout = autorestart_timeout

        self._tracker = None
        self._restart_thread = None
        self._kill_thread = Event()
        self._is_running = False
        self._last_ip = None

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

    def _ip_updated(self, ip: str):
        if ip != self._last_ip:
            self._last_ip = ip
            if self._callback is not None:
                self._callback(ip)

    def _start_tracker(self):
        try:
            self._tracker = self._tracker_factory()
            self._tracker.register_callback(self._ip_updated)
            self._tracker.start()
        except Exception:
            self.log().error("Exception on starting tracker", exc_info=True)

    def _stop_tracker(self):
        try:
            if self._tracker is not None:
                self._tracker.stop()
        except Exception:
            self.log().error("Exception on stopping tracker", exc_info=True)

    def _run(self):
        self._start_tracker()
        while not self._kill_thread.wait(self._autorestart_timeout):
            self._stop_tracker()
            self.log().debug("Restarting tracker...")
            self._start_tracker()
        self._stop_tracker()


def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

    def print_new_ip(ip):
        logging.info("New IP address: %s" % ip)

    def gimme_tracker():
        return NetlinkIPAddressTracker(False)

    monitor = Monitor(gimme_tracker, print_new_ip, 60)
    monitor.start()
    time.sleep(10 * 6)
    monitor.stop()


if __name__ == '__main__':
    main()
