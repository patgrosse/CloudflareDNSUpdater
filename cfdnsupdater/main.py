import argparse
import logging
import signal
import sys
import time
from configparser import ConfigParser
from ipaddress import IPv4Address, IPv6Address
from typing import Union

from CloudFlare import CloudFlare

from cfdnsupdater.cftools import CFTools, CFToolException
from cfdnsupdater.helper import Loggable
from cfdnsupdater.tracker import NetlinkIPAddressTracker, IpifyIPAddressTracker, SocketIPAddressTracker, Monitor


class Main(Loggable):
    def main(self):
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        parser = argparse.ArgumentParser(description="Tool for keeping a DNS record at Cloudflare up to date with "
                                                     "dynamically changing IP adresses",
                                         formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("--config", required=True, help="Path to config file with credentials etc.", metavar="FILE",
                            type=argparse.FileType('r'))
        ip_group = parser.add_mutually_exclusive_group(required=True)
        ip_group.add_argument("-4", "--ipv4", dest="ip_version", action="store_const", const=4,
                              help="Retrieve IPv4 addresses")
        ip_group.add_argument("-6", "--ipv6", dest="ip_version", action="store_const", const=6,
                              help="Retrieve IPv6 addresses")
        # modes
        mode_group = parser.add_mutually_exclusive_group(required=True)
        mode_group.add_argument("--manual", dest="mode", action="store_const", const="manual",
                                help="Update IP address once")
        mode_group.add_argument("--auto", dest="mode", action="store_const", const="auto",
                                help="Keep track of IP address changes and update accordingly")
        auto_group = parser.add_argument_group("Auto mode specific")
        auto_group.add_argument("--restart", type=int,
                                help="Interval in seconds to restart the tracker as a safety measure (default: 1 day)",
                                metavar="SEC", default=86400)

        # tracker
        tracker_parser = parser.add_subparsers(metavar="TRACKER", help="'netlink': use Linux netlink API to keep "
                                                                       "track of local IP address changes (does "
                                                                       "not work for NAT)\n'ipify': use ipify "
                                                                       "service to determine IP address, "
                                                                       "periodic checks (works for "
                                                                       "NAT)\n'socket': open a socket and use "
                                                                       "the used local IP address, update in an "
                                                                       "interval (more privacy, does not work "
                                                                       "for NAT)",
                                               dest="tracker")
        tracker_parser.required = True

        # # netlink tracker
        nat_parser = tracker_parser.add_parser("netlink", description="Use Linux netlink API to keep "
                                                                      "track of local IP address changes (does "
                                                                      "not work for NAT)")
        nat_parser.add_argument("--interface", help="Name of the interface to be watched", metavar="IFNAME")
        # # ipify tracker
        ipify_parser = tracker_parser.add_parser("ipify", description="Use ipify service to "
                                                                      "determine IP address (works for "
                                                                      "NAT), has to check periodically if used in "
                                                                      "auto mode")
        ipify_parser.add_argument("--interval", type=int, help="Update interval in seconds", metavar="SEC")
        # # socket tracker
        socket_parser = tracker_parser.add_parser("socket", description="open a socket and use "
                                                                        "the used local IP address (more privacy, "
                                                                        "does not work for NAT), has to check "
                                                                        "periodically if used in auto mode")
        socket_parser.add_argument("--interval", type=int, help="Update interval in seconds", metavar="SEC")

        args = parser.parse_args()

        config = ConfigParser()
        config.read_file(args.config)
        email = config.get("api", "email")
        token = config.get("api", "token")
        zone_name = config.get("record", "zone")
        rname = config.get("record", "name")
        ipv6 = (args.ip_version == 6)

        cf = CloudFlare(email=email, token=token)
        cft = CFTools(cf)

        zone_id = cft.get_zone_id_by_name(zone_name)
        self.log().info("Using zone: %s %s" % (zone_id, zone_name))

        if args.mode == "auto":
            def create_tracker():
                if args.tracker == "netlink":
                    return NetlinkIPAddressTracker(ipv6, args.interface)
                elif args.tracker == "ipify":
                    return IpifyIPAddressTracker(ipv6, args.interval)
                elif args.tracker == "socket":
                    return SocketIPAddressTracker(ipv6, args.interval)
                else:
                    raise Exception("Unexpected tracker type %s", args.tracker)

            def update_ip(ip):
                # type: (Union[IPv4Address, IPv6Address]) -> None
                try:
                    cft.perform_update(zone_id, rname, "AAAA" if ipv6 else "A", ip)
                except CFToolException:
                    self.log().exception("Exception on updating IP address")

            monitor = Monitor(create_tracker, update_ip, args.restart)
            monitor.start()

            def sigterm_handler(_signo, _stack_frame):
                self.log().info("Caught SIGTERM, stopping...")
                sys.exit(0)

            signal.signal(signal.SIGTERM, sigterm_handler)

            while True:
                try:
                    time.sleep(100)
                except KeyboardInterrupt:
                    self.log().info("Caught SIGINT, stopping...")
                    monitor.stop()
                    break

        elif args.mode == "manual":
            if args.tracker_man == "ipify":
                tracker = IpifyIPAddressTracker(args.ip_version == 6, 1)
            elif args.tracker_man == "socket":
                tracker = SocketIPAddressTracker(args.ip_version == 6, 1)
            else:
                raise Exception("Unexpected manual tracker type %s", args.tracker)
            current_ip = tracker.get_current()
            if current_ip is None:
                self.log().error("Couldn't find a valid external IP address!")
            else:
                cft.perform_update(zone_id, rname, "AAAA" if ipv6 else "A", current_ip)
        else:
            raise Exception("Unexpected mode %s" % args.mode)
