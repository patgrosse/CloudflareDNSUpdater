from typing import Dict, List

from CloudFlare import CloudFlare, exceptions

from cfdnsupdater.helper import Loggable


class CFToolException(Exception):
    def __init__(self, msg: str):
        super(CFToolException, self).__init__(msg)


class CFTools(Loggable):
    _cf: CloudFlare

    def __init__(self, cf: CloudFlare):
        super().__init__()
        self._cf = cf

    def get_zone_id(self, zone_name: str):
        try:
            zones = self._cf.zones.get(params={"name": zone_name, "per_page": 1})
        except exceptions.CloudFlareAPIError as e:
            raise CFToolException("/zones.get %d %s - api call failed" % (int(e), e))
        except Exception as e:
            raise CFToolException("/zones.get - %s - api call failed" % e)

        if len(zones) == 0:
            raise CFToolException("No zones found")

        zone = zones[0]
        return zone["id"]

    def get_dns_records(self, zone_id: str):
        try:
            return self._cf.zones.dns_records.get(zone_id)
        except exceptions.CloudFlareAPIError as e:
            raise CFToolException("/zones/dns_records.get %d %s - api call failed" % (int(e), e))

    @staticmethod
    def filter_dns_record(dns_records: List[Dict[str, str]], dtype: str, name: str) -> Dict[str, str]:
        for dns_record in dns_records:
            if dns_record["type"] == dtype and dns_record["name"] == name:
                return dns_record
        raise CFToolException("Could not find matching DNS entry with type %s and name %s" % (dtype, name))

    def update_dns_record(self, zone_id: str, dns_record: Dict[str, str]):
        try:
            return self._cf.zones.dns_records.put(zone_id, dns_record["id"], data=dns_record)
        except exceptions.CloudFlareAPIError as e:
            raise CFToolException("/zones.dns_records.post %s - %d %s" % (dns_record["name"], int(e), e))

    def get_existing_dns_record(self, zone_id: str, rname: str, rtype: str):
        dns_records = self.get_dns_records(zone_id)
        self.log().debug("Found existing DNS records:")
        # then all the DNS records for that zone
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

        return self.filter_dns_record(dns_records, rtype, rname)

    def perform_update(self, zone_id: str, rname: str, rtype: str, ip: str):
        dns_record = self.get_existing_dns_record(zone_id, rname, rtype)

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
