import configparser
import sys

from cfdnsupdater.tools import *


def main():
    if len(sys.argv) != 2:
        exit("Use: %s <configfile>" % sys.argv[0])
    cp = configparser.ConfigParser()
    cp.read(sys.argv[1])
    cf = CloudFlare(email=cp.get("api", "email"), token=cp.get("api", "token"))
    zone_name = cp.get("record", "zone")
    zone_id = get_zone_id(cf, zone_name)
    print("Using zone:")
    print(" %s %s" % (zone_id, zone_name))

    dns_records = get_dns_records(cf, zone_id)
    print("Found existings DNS records:")
    # then all the DNS records for that zone
    for dns_record in dns_records:
        print(" %s %20s %6d %-5s %s ; proxied=%s proxiable=%s" % (
            dns_record["id"],
            dns_record["name"],
            dns_record["ttl"],
            dns_record["type"],
            dns_record["content"],
            dns_record["proxied"],
            dns_record["proxiable"]
        ))

    rname = cp.get("record", "name")
    rtype = cp.get("record", "type")
    dns_record = filter_dns_record(dns_records, rtype, rname)
    rcontent = retrieve_record_content(rtype)

    print("Updating record with name %s and type %s with content %s" % (rname, rtype, rcontent))
    dns_record["content"] = rcontent
    response = update_dns_record(cf, zone_id, dns_record)

    print("Response:")
    print(" %s %20s %6d %-5s %s ; proxied=%s proxiable=%s" % (
        response["id"],
        response["name"],
        response["ttl"],
        response["type"],
        response["content"],
        response["proxied"],
        response["proxiable"]
    ))
