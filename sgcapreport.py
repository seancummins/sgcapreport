#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
sgcapreport.py - Reports capacity per Storage Group

Requirements:
- Python 2.7.x
- prettytable -- "pip install prettytable" to install
- EMC Solutions Enabler
- SYMCLI bin directory in PATH

"""

import argparse
import os
import subprocess
from prettytable import PrettyTable
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

### Define and Parse CLI arguments
parser = argparse.ArgumentParser(description='Reports capacity per Symmetrix Storage Group.')
rflags = parser.add_argument_group('Required arguments')
rflags.add_argument('-sid',      required=True, help='Symmetrix serial number')
#rflags.add_argument('-offline',  required=True, help='Offline SYMAPIDB filename')
sflags = parser.add_argument_group('Additional optional arguments')
sflags.add_argument('-nochildren',         help='Flag; Skips reporting on Child Storage Groups', action="store_true")
sflags.add_argument('-csv',                help='Flag; Outputs in CSV format', action="store_true")


args = parser.parse_args()

#os.environ['SYMCLI_OFFLINE'] = '1'
#os.environ['SYMCLI_DB_FILE'] = os.path.abspath(args.offline)

### Capture SYMCLI TDEV information into ElementTree
tdevcommand = "symcfg -sid " + args.sid + " list -tdev -gb -output xml_e"
tdev_xml = subprocess.check_output(tdevcommand, shell=True)
tdevtree = ET.fromstring(tdev_xml)

### Put TDEV ElementTree values into Python data structure
# tdevcap{ 'tdev1': [1024, 512, 512] }   # [total, allocated, written]
tdevcap = dict()

# Iterate through all TDEVs, capturing capacity information
for elem in tdevtree.iterfind('Symmetrix/ThinDevs/Device'):
    tdevcap[elem.find('dev_name').text] = [float(elem.find('total_tracks_gb').text), float(elem.find('alloc_tracks_gb').text), float(elem.find('written_tracks_gb').text)]


### Capture SYMCLI SG information into ElementTree
sgcommand = "symsg -sid " + args.sid + " list -v -output xml_e"
symsg_xml = subprocess.check_output(sgcommand, shell=True)
sgtree = ET.fromstring(symsg_xml)

### Put SG ElementTree values into Python data structure
# sgcapacity{ 'sg1': [1024, 512, 512] }   # [total, allocated, written]
sgcapacity = dict()
# sgparents { 'sg1': [ 'parentsg1', 'parentsg2', 'parentsg3']}
sgparents = dict()
# sgchildren{ 'sg1': [ 'childsg1', 'childsg2', 'childsg3']}
sgchildren = dict()

# Iterate through all SGs
for elem in sgtree.iterfind('SG'):
    # Initialize data structures to default values
    sgname = elem.find('SG_Info/name').text    # Current Storage Group name
    sgcapacity[sgname] = [0, 0, 0]
    sgchildren[sgname] = list()
    sgparents[sgname] = list()
    # Iterate through an SG's device members for members and their capacity
    for member in elem.iterfind('DEVS_List/Device'):
        membername = member.find('dev_name').text       # Current SymDev (member) name
        if membername in tdevcap:
        # We've found a TDEV; record actual total/allocated/written capacity
            devcapacity = tdevcap[membername]
        else:
        # We've found a Non-TDEV (e.g. STD); report all capacity values as total capacity
            stdcap = float(member.find('megabytes').text)/1024
            devcapacity = [stdcap, stdcap, stdcap]
        # Add this device's capacity info to the running tally for this SG
        sgcapacity[sgname] = map(sum, zip(sgcapacity[sgname], devcapacity))
    # Iterate through an SG's SG members for Parent/Child information
    for cascadesg in elem.iterfind('SG_Info/SG_group_info/SG'):
        if cascadesg.find('Cascade_Status').text == 'IsChild':
        # We've found a Child SG; add it to the sgchildren[sgname] dictionary
            childname = cascadesg.find('name').text
            if childname not in sgchildren[sgname]:
                sgchildren[sgname].append(childname)
        elif cascadesg.find('Cascade_Status').text == 'IsParent':
        # We've found a Parent SG; add it to the sgparents[sgname] dictionary
            parentname = cascadesg.find('name').text
            if parentname not in sgparents[sgname]:
                sgparents[sgname].append(parentname)


# Build the PrettyTable
if args.csv:
    print "Storage Group,Total GB,Allocated GB,Written GB,Parents,Children"


report = PrettyTable(["Storage Group", "Total GB", "Allocated GB", "Written GB", "Parents", "Children"])
for sg, mb in sgcapacity.items():
    children, parents = ["", ""]
    if sg in sgchildren:
        children = ",".join(sgchildren[sg])
    if sg in sgparents:
        if args.nochildren:
            continue
        else:
            parents = ",".join(sgparents[sg])
    if args.csv:
        print ",".join([sg, str(sgcapacity[sg][0]), str(sgcapacity[sg][1]), str(sgcapacity[sg][2]), parents, children])
    else:
        report.add_row([sg, sgcapacity[sg][0], sgcapacity[sg][1], sgcapacity[sg][2], parents, children])


# Format and print
report.int_format = "10"
report.float_format = "10.1"
report.max_width["Children"] = 30
report.format = True
if not args.csv:
    print report
