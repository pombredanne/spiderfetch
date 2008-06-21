#!/usr/bin/env python

import re
import urlparse

import spider


_scheme = "(?P<scheme>%s)$" % "".join(reduce(lambda x, y: "%s|%s" % (x, y), spider.SPIDER_SCHEMES))
scheme_regex = re.compile(_scheme)

class InvalidUrl(Exception): pass

def rewrite_scheme(scheme):
    m = re.search(scheme_regex, scheme)
    if m and m.groups():
        return m.group('scheme')
    return scheme

def assemble_netloc(username, password, hostname, port):
    netloc = hostname
    if username:
        if password:
            username = "%s:%s" % (username, password)
        netloc = "%s@%s" % (username, hostname)
    if port:
        netloc = "%s:%s" % (netloc, port)
    return netloc

def rewrite_urls(origin_url, urls):
    origin_pack = urlparse.urlsplit(origin_url)
    for u in urls:
        # kill breaks
        if u:
            u = re.sub("(\n|\t)", "", u)

        pack = urlparse.urlsplit(u)
        (scheme, netloc, path, query, fragment) = pack

        # try to rewrite scheme
        scheme = rewrite_scheme(pack.scheme)

        # rewrite netloc to include credentials
        if origin_pack.username and pack.hostname == origin_pack.hostname:
            netloc = assemble_netloc(origin_pack.username,\
                        origin_pack.password, pack.hostname, pack.port)

        # reassemble into url
        new_u = urlparse.urlunsplit((scheme, netloc, path, query, None))

        # no scheme or netloc, it's a path on-site
        if not scheme and not netloc and path:
            path_query = urlparse.urlunsplit((None, None, path, query, None))
            new_u = urlparse.urljoin(origin_url, path_query)

        if new_u:
            yield new_u

        # XXX error handling

def unique(it):
    seen = set()
    return [x for x in it if x not in seen and not seen.add(x)]



if __name__ == "__main__":
    base = "http://user:pass@www.juventuz.com/forum/search.php?searchid=1186852"
    urls = ["../index.php?name=jack&act=whatever",
            "http://www.juventuz.com/matches"]
    for u in rewrite_urls(base, urls):
        print u
