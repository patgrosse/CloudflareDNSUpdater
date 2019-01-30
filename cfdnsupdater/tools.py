import socket
from typing import Dict, List

from CloudFlare import CloudFlare, exceptions


def get_zone_id(cf: CloudFlare, zone_name: str):
    zones = None
    try:
        zones = cf.zones.get(params={"name": zone_name, "per_page": 1})
    except exceptions.CloudFlareAPIError as e:
        exit("/zones.get %d %s - api call failed" % (int(e), e))
    except Exception as e:
        exit("/zones.get - %s - api call failed" % e)

    if len(zones) == 0:
        exit("No zones found")

    zone = zones[0]
    return zone["id"]


def get_dns_records(cf: CloudFlare, zone_id: str):
    try:
        return cf.zones.dns_records.get(zone_id)
    except exceptions.CloudFlareAPIError as e:
        exit("/zones/dns_records.get %d %s - api call failed" % (int(e), e))


def filter_dns_record(dns_records: List[Dict[str, str]], dtype: str, name: str) -> Dict[str, str]:
    for dns_record in dns_records:
        if dns_record["type"] == dtype and dns_record["name"] == name:
            return dns_record
    exit("Could not find matching DNS entry with type %s and name %s" % (dtype, name))


def update_dns_record(cf: CloudFlare, zone_id: str, dns_record: Dict[str, str]):
    try:
        return cf.zones.dns_records.put(zone_id, dns_record["id"], data=dns_record)
    except exceptions.CloudFlareAPIError as e:
        exit("/zones.dns_records.post %s - %d %s" % (dns_record["name"], int(e), e))


def retrieve_record_content(dtype: str):
    if dtype == "A":
        print("Retrieving machines external IPv4 address...")
        return get_ipv4()
    elif dtype == "AAAA":
        print("Retrieving machines external IPv6 address...")
        return get_ipv6()
    else:
        exit("Cannot update DNS records of type %s" % dtype)


def get_ipv4():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Use CloudFlare DNS server to determine IPv4
    s.connect(("1.1.1.1", 80))
    ipv4 = s.getsockname()[0]
    s.close()
    return ipv4


def get_ipv6():
    s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    # Use CloudFlare DNS server to determine IPv6
    s.connect(("2606:4700:4700::1111", 80))
    ipv6 = s.getsockname()[0]
    s.close()
    return ipv6
