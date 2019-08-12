from typing import Dict, List, Optional

from CloudFlare import CloudFlare

from cfdnsupdater.helper import Loggable


class CFToolException(Exception):
    pass


class CFTools(Loggable):
    __slots__ = ("_cf",)

    def __init__(self, cf):
        # type: (CloudFlare) -> None
        self._cf = cf  # type: CloudFlare

    def get_zone_id_by_name(self, zone_name):
        # type: (str) -> str
        try:
            zones = self._cf.zones.get(params={"name": zone_name, "per_page": 1})
        except Exception as e:
            raise CFToolException("zones.get failed with exception for zone name %s" % zone_name, e)

        if len(zones) == 0:
            raise CFToolException("No zones found")

        zone = zones[0]
        return zone["id"]

    def get_dns_records_by_zone(self, zone_id):
        # type: (str) -> List[Dict[str,]]
        try:
            return self._cf.zones.dns_records.get(zone_id)
        except Exception as e:
            raise CFToolException("dns_records.get failed with exception for zone_id %s" % zone_id, e)

    def update_dns_record(self, zone_id, dns_record):
        # type: (str, Dict[str,]) -> Dict[str,]
        try:
            return self._cf.zones.dns_records.put(zone_id, dns_record["id"], data=dns_record)
        except Exception as e:
            raise CFToolException("dns_records.get failed with exception for zone_id %s and dns_record %r"
                                  % (zone_id, dns_record), e)

    @staticmethod
    def filter_dns_record(dns_records, rtype, rname):
        # type: (List[Dict[str,]], str, str) -> Optional[Dict[str]]
        for dns_record in dns_records:
            if dns_record["type"] == rtype and dns_record["name"] == rname:
                return dns_record
        return None

    def perform_update(self, zone_id, rname, rtype, ip):
        # type: (str, str, str, str) -> None
        dns_records = self.get_dns_records_by_zone(zone_id)
        self.log().debug("Found existing DNS records:")
        for dns_record in dns_records:
            self.log().debug(" %s %20s %6d %-5s %s ; proxied=%s proxiable=%s" % (
                dns_record["id"],
                dns_record["name"],
                dns_record["ttl"],
                dns_record["type"],
                dns_record["content"],
                dns_record["proxied"],
                dns_record["proxiable"]
            ))

        dns_record = self.filter_dns_record(dns_records, rtype, rname)
        if not dns_record:
            raise CFToolException("Could not find matching DNS entry with type %s and name %s" % (rtype, rname))

        self.log().info("Updating record with name %s and type %s with content %s" % (rname, rtype, ip))
        if dns_record["content"] == ip:
            self.log().info("No need for an update")
        else:
            self.log().info("Updating with new content %s" % ip)
            dns_record["content"] = ip
            response = self.update_dns_record(zone_id, dns_record)

            self.log().debug("Response:")
            self.log().debug(" %s %20s %6d %-5s %s ; proxied=%s proxiable=%s" % (
                response["id"],
                response["name"],
                response["ttl"],
                response["type"],
                response["content"],
                response["proxied"],
                response["proxiable"]
            ))
