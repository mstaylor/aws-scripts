#
# Gateway Grabber - 2014-02-27
# joe@uberboxen.net
# bud.staylor@gmail.com
# Repoints the default gw for a routing table to the current instance
# that is running this script.
#
#

import boto
import boto.utils
import os
import sys

dry_run = False

# AWS access/secret keys (None if using EC2 role)
aws_access      = None
aws_secret      = None
subnet_id = None
vpc_conn = None


try:
    instance_id = boto.utils.get_instance_metadata()['instance-id']

    if instance_id is None:
        print "Did not receive an instance id from isntmetadata"
        sys.exit(1)
    print "instance id is %s\n" % instance_id

    az = boto.utils.get_instance_metadata()['placement']['availability-zone']
    if az is None:
        print "Did not receive an availability zone from metadata"
        sys.exit(1)
    print "Instance Availability Zone is %s\n" % az

    mac = boto.utils.get_instance_metadata()['mac']
    if mac is None:
        print "Did not receive a mac address from instance metadata"
        sys.exit(1)
    print "Instance mac address is %s\n" % mac

    current_subnet_id = boto.utils.get_instance_metadata()['network']['interfaces']['macs'][mac]['subnet-id']
    if current_subnet_id is None:
        print "Did not receive a subnet id from instance metadata"
        sys.exit(1)
    print "current subnet id for instance is %s" % current_subnet_id

    vpc_id = boto.utils.get_instance_metadata()['network']['interfaces']['macs'][mac]['vpc-id']
    if vpc_id is None:
        print "Did not receive a vpc id from instance metadata"
        sys.exit(1)
    print "current vpc id for instance is %s" % vpc_id
    vpc_conn = boto.connect_vpc(aws_access_key_id=aws_access, aws_secret_access_key=aws_secret)
    subnets = vpc_conn.get_all_subnets(filters={'availabilityZone': az, 'vpcId': vpc_id})
    for subnet in subnets:
        print "current subnet to check is %s" % subnet.id
        if subnet.id != current_subnet_id:
            subnet_id = subnet.id
            break

    if subnet_id is None:
        print "Did not find a second subnet"
        sys.exit(1)

    print "subnet_id is %s" % subnet_id

except:
    print "Could not get EC2 instance ID!"
    sys.exit(1)

ec2_conn = boto.connect_ec2(aws_access_key_id=aws_access, aws_secret_access_key=aws_secret)
final_route = None

try:
    routes = vpc_conn.get_all_route_tables(filters={'association.subnet-id': subnet_id, 'association.main': 'false'})
    for rt in routes:
        final_route = rt
        gw_route = next((route for route in rt.routes if route.destination_cidr_block == '0.0.0.0/0' and route.gateway_id is not None), None)
        if gw_route is not None:
            final_route = None

except Exception, e:
    print "Could not find route table [%s]: %s" % (subnet_id, e)
    sys.exit(1)

if final_route is None:
    print "Could not find route table [%s]" % (subnet_id)
    sys.exit(1)

print "Found the route table: %s" % (rt.id,)

source_dest_check = ec2_conn.get_instance_attribute(instance_id, 'sourceDestCheck')['sourceDestCheck']

print "Source/Dest check: %s" % (source_dest_check,)

if source_dest_check:
    print "Instance must have source/dest checking disabled to NAT properly!"
    try:
        ec2_conn.modify_instance_attribute(instance_id, 'sourceDestCheck', False, dry_run=dry_run)
    except Exception, e:
        print "Could not modify source/dest check: %s" % (e,)
        sys.exit(1)

gw_route = next((route for route in final_route.routes if route.destination_cidr_block == '0.0.0.0/0'), None)
if not gw_route:
    print "Could not find default gw route in routing table!"
else:
    print "Found a gateway route: %s, %s, %s" % (final_route.id, gw_route.destination_cidr_block, instance_id)
    try:
        vpc_conn.delete_route(final_route.id, '0.0.0.0/0', dry_run=dry_run)
    except Exception, e:
        print "Could not delete gw route! %s" % (e,)
        sys.exit(1)

try:
    vpc_conn.create_route(final_route.id, '0.0.0.0/0', instance_id=instance_id, dry_run=dry_run)
except Exception, e:
    print "Could not replace gw route! %s" % (e,)
    sys.exit(1)

print "Route table updated!"