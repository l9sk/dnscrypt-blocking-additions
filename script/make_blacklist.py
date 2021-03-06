#! /usr/bin/env python2.7

# run with py -2 make_blacklist.py

import argparse
import re
import sys
import urllib2
import codecs

def parse_list(content, trusted=False):
    rx_comment = re.compile(r'^(#|$)')
    rx_inline_comment = re.compile(r'\s*#\s*[a-z0-9-].*$')
    rx_u = re.compile(r'^@*\|\|([a-z0-9.-]+[.][a-z]{2,})\^?(\$(popup|third-party))?$')
    rx_l = re.compile(r'^([a-z0-9.-]+[.][a-z]{2,})$')
    rx_h = re.compile(r'^[0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,3}\s+([a-z0-9.-]+[.][a-z]{2,})$')
    rx_mdl = re.compile(r'^"[^"]+","([a-z0-9.-]+[.][a-z]{2,})",')
    rx_b = re.compile(r'^([a-z0-9.-]+[.][a-z]{2,}),.+,[0-9: /-]+,')
    rx_dq = re.compile(r'^address=/([a-z0-9.-]+[.][a-z]{2,})/.')
    rx_trusted = re.compile(r'^([*a-z0-9.-]+)$')

    names = set()
    rx_set = [rx_u, rx_l, rx_h, rx_mdl, rx_b, rx_dq]
    if trusted:
        rx_set = [rx_trusted]
    for line in content.splitlines():
        line = str.lower(str.strip(line))
        if rx_comment.match(line):
            continue
        line = rx_inline_comment.sub('', line)
        for rx in rx_set:
            matches = rx.match(line)
            if not matches:
                continue
            name = matches.group(1)
            names.add(name)
    return names


def load_from_url(url):
    sys.stderr.write("Loading data from [{}]\n".format(url))
    # Some lists seem to intentionally 404 the default user-agent...
    # Taken from https://techblog.willshouse.com/2012/01/03/most-common-user-agents/
    req = urllib2.Request(url=url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'})
    trusted = False
    if req.get_type() == "file":
        trusted = True
    response = None
    try:
        response = urllib2.urlopen(req, timeout=int(args.timeout))
    except urllib2.URLError as err:
        raise Exception("[{}] could not be loaded: {}\n".format(url, err))
    if trusted is False and response.getcode() != 200:
        raise Exception("[{}] returned HTTP code {}\n".format(url, response.getcode()))
    content = response.read()

    return (content, trusted)


def name_cmp(name):
    parts = name.split(".")
    parts.reverse()
    return str.join(".", parts)


def has_suffix(names, name):
    parts = str.split(name, ".")
    while parts:
        parts = parts[1:]
        if str.join(".", parts) in names:
            return True

    return False


def whitelist_from_url(url):
    if not url:
        return set()
    content, trusted = load_from_url(url)

    return parse_list(content, trusted)


def domainlist_from_config_file(file, outfile, whitelist, time_restricted_url, ignore_retrieval_failure):
    blacklists = {}
    whitelisted_names = set()
    all_names = set()
    unique_names = set()

    # Load conf & blacklists
    with open(file) as fd:
        for line in fd:
            line = str.strip(line)
            if str.startswith(line, "#") or line == "":
                continue
            obfus = False
            if str.startswith(line, "obfus "):
                obfus = True
                url = line[6:]
            else:
                url = line
            try:
                content, trusted = load_from_url(url)
                if obfus:
                    content = codecs.encode(content, 'rot_13')
                names = parse_list(content, trusted)
                blacklists[url] = names
                all_names |= names
            except Exception as e:
                sys.stderr.write(e.message)
                if not ignore_retrieval_failure:
                    exit(1)

    # Time-based blacklist
    if time_restricted_url and not re.match(r'^[a-z0-9]+:', time_restricted_url):
        time_restricted_url = "file:" + time_restricted_url

    if time_restricted_url:
        time_restricted_content, trusted = load_from_url(time_restricted_url)
        time_restricted_names = parse_list(time_restricted_content)

        if time_restricted_names:
            outfile.write("########## Time-based blacklist ##########\n")
            for name in time_restricted_names:
                outfile.write(name)

        # Time restricted names should be whitelisted, or they could be always blocked
        whitelisted_names |= time_restricted_names

    # Whitelist
    if whitelist and not re.match(r'^[a-z0-9]+:', whitelist):
        whitelist = "file:" + whitelist

    whitelisted_names |= whitelist_from_url(whitelist)

    # Process blacklists
    for url, names in blacklists.items():
        outfile.write("\n\n########## Blacklist from {} ##########\n".format(url))
        ignored, whitelisted = 0, 0
        list_names = list()
        for name in names:
            if has_suffix(all_names, name) or name in unique_names:
                ignored = ignored + 1
            elif has_suffix(whitelisted_names, name) or name in whitelisted_names:
                whitelisted = whitelisted + 1
            else:
                list_names.append(name)
                unique_names.add(name)

        list_names.sort(key=name_cmp)
        if ignored:
            outfile.write("# Ignored duplicates: {}\n".format(ignored))
        if whitelisted:
            outfile.write("# Ignored entries due to the whitelist: {}\n".format(whitelisted))
        for name in list_names:
            outfile.write("{}\n".format(name))


argp = argparse.ArgumentParser(description="Create a unified blacklist from a set of local and remote files")
argp.add_argument("-c", "--config", default="blacklist.conf",
    help="file containing blacklist sources")
argp.add_argument("-w", "--whitelist", default="whitelist.conf",
    help="file containing a set of names to exclude from the blacklist")
argp.add_argument("-r", "--time-restricted", default="time-restricted.txt",
    help="file containing a set of names to be time restricted")
argp.add_argument("-i", "--ignore-retrieval-failure", action='store_true',
    help="generate list even if some urls couldn't be retrieved")
argp.add_argument("-t", "--timeout", default=30,
    help="URL open timeout")
args = argp.parse_args()

time_restricted = args.time_restricted
ignore_retrieval_failure = args.ignore_retrieval_failure

wf = open('whitelist.tmp', 'w')
domainlist_from_config_file(args.whitelist, wf, None, time_restricted, ignore_retrieval_failure)
wf.close()

f = open('blacklist.txt', 'w')
domainlist_from_config_file(args.config, f, "whitelist.tmp", time_restricted, ignore_retrieval_failure)
f.close()
