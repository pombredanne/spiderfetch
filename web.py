#!/usr/bin/env python

import pickle
import sqlite3
import sys
import UserDict

import io
import shcolor


import os; os.path.exists('db.websq') and os.unlink('db.websq')
conn = sqlite3.connect('db.websq')
conn.row_factory = sqlite3.Row
c = conn.cursor()

class DBDict(UserDict.IterableUserDict):
    def __init__(self, table):
        self.table = table
        UserDict.IterableUserDict.__init__(self)

    def __getitem__(self, url):
        return Node(url)

    def get(self, url):
        return self.__getitem__(url)

    def __iter__(self):
        for f in c.execute('select * from %s' % self.table):
            yield f['docurl']

    def __setitem__(self, url, node):
        global conn, c
        try:
            c.execute('insert into %s values (?, null)' % self.table, (url,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass

    def __delitem__(self, url):
        global conn, c
        c.execute('delete from %s where docurl=?' % self.table, (url,))
        conn.commit()

    def __contains__(self, url):
        global conn, c
        for e in c.execute('select count(*) from %s where docurl=?' % self.table, (url,)):
            return e[0]

    def __len__(self):
        global conn, c
        for e in c.execute('select count(*) from %s' % self.table):
            return e[0]

    def __str__(self):
        global conn, c
        return ", ".join(t for t in self.__iter__())
        
class DBDictDouble(DBDict):
    def __init__(self, table, nodeurl):
        self.nodeurl = nodeurl
        DBDict.__init__(self, table)

    def __getitem__(self, url):
        return Node(url)

    def __setitem__(self, url, node):
        global conn, c
        try:
            c.execute('insert into %s values (?, ?)' % self.table,
                      (self.nodeurl, node.url))
            conn.commit()
        except sqlite3.IntegrityError:
            pass

    def __delitem__(self, url):
        global conn, c
        c.execute('delete from %s where docurl=?' % self.table, (url,))
        conn.commit()

    def __str__(self):
        global conn, c
        return ", ".join(str(t['linkurl']) for t in
             c.execute('select * from %s where docurl=?' % self.table, (self.nodeurl,)))

class Node(object):
    def __init__(self, url):
        self.url = url
        self.incoming = DBDictDouble('node_in', url)
        self.outgoing = DBDictDouble('node_out', url)
        self.aliases = [url]

class Web(object):
    def __init__(self, root=None, existing=False):
        global conn, c
        if not existing:
            c.execute('create table node (docurl text primary key, is_root boolean)')
            c.execute('create table node_in (docurl text, linkurl text)')
            c.execute('create table node_out (docurl text, linkurl text)')
            c.execute('create table node_ref (refurl text, docurl text)')
            conn.commit()

        self.index = DBDict('node')
        if root:
            self.add_url(root, [])

    def set_root(self, node):
        global conn, c
        try:
            c.execute('insert into node values (?, ?)', (node.url, True))
        except sqlite3.IntegrityError:
            c.execute('update node set is_root=? where docurl=?', (True, node.url))
        c.execute('update node set is_root=? where docurl!=?', (False, node.url))
        conn.commit()

    def get_root(self):
        global conn, c
        for e in c.execute('select docurl from node where is_root=?', (True,)):
            return Node(e['docurl'])

    root = property(fget=get_root, fset=set_root)

    def __contains__(self, e):
        return e in self.index

    def __str__(self):
        return str(self.index)

    def urls(self):
        return self.index.keys()

    def add_url(self, url, children):
        if url not in self.index:
            self.index[url] = Node(url)
        node = self.index[url]

        if not self.root:
            self.root = node

        for c_url in children:
            if not c_url == url:
                if c_url not in self.index:
                    self.index[c_url] = Node(c_url)
                n = self.index[c_url]
                n.incoming[node.url] = node
                node.outgoing[n.url] = n

    def add_ref(self, url, new_url):
        self.index[new_url] = self.index[url]
        self.index[url].aliases.append(new_url)

    def get(self, url):
        return self.index.get(url)

    ### Introspective

    def dump(self):
        for u in self.index:
            io.write_out("%s\n" % u)

    def assert_in_web(self, url):
        if url not in self.index:
            io.write_err("Url %s not in the web\n" %
                         shcolor.color(shcolor.YELLOW, url))
            sys.exit(1)
        
    def print_refs(self, url, out=True):
        self.assert_in_web(url)
        node = self.index.get(url)
        l = node.outgoing
        if not out: l = node.incoming
        for u in l:
            io.write_out("%s\n" % u)

    def print_aliases(self, url):
        self.assert_in_web(url)
        for u in self.index.get(url).aliases:
            io.write_out("%s\n" % u)

    def get_trace(self, url):
        self.assert_in_web(url)
        seen = {}
        paths = [[url]]
        seen[url] = True
        while paths:
            paths_next = []
            for path in paths:
                if self.index[path[0]] == self.root:
                    return path
                for url in self.index.get(path[-1]).incoming:
                    if url not in seen:     # loop detected, drop this path
                        seen[url] = True
                        newpath = path[:]   # careful, this is a copy, not ref!
                        newpath.append(url)
                        if self.index[url] == self.root:
                            newpath.reverse()
                            return newpath
                        paths_next.append(newpath)
            paths = paths_next

    # is this supposed to be longest (in graph) or deepest (from root)?
    def deepest_url(self):
        paths = []
        for url in self.index:
            paths.append(self.get_trace(url))
        longest = paths[0]
        for path in paths:
            if len(path) > len(longest):
                longest = path
        return longest

    def print_trace(self, path):
        if path:
            io.write_err("Showing trace from root:\n")
            for (i, hop) in enumerate(path):
                io.write_err(" %s  %s\n" % (str(i).rjust(1+(len(path)/10)), hop))

    def print_popular(self):
        tuples = [(len(n.incoming), n) for n in self.index.values()]
        tuples.sort(reverse=True)
        ln = len(str(tuples[0][0]).rjust(2))
        io.write_err("Showing most referenced urls:\n")
        for (i, node) in tuples[:10]:
            io.write_err(" %s  %s\n" % (str(i).rjust(ln), node.url))

    def print_multiple(self):
        ss = []
        for n in self.index.values():
            if len(n.aliases) > 1:
                pair = (len(n.aliases), n.aliases)
                if pair not in ss:
                    ss.append(pair)
        if ss:
            ss.sort(reverse=True)
            ln = len(str(ss[0][0]))  # length of highest count
            io.write_err("Showing documents with multiple urls:\n")
            for pair in ss:
                (count, aliases) = pair
                for url in aliases:
                    prefix = "".rjust(ln)
                    if aliases.index(url) == 0:
                        prefix = str(count).rjust(ln)
                    io.write_err(" %s  %s\n" % (prefix, url))
                if not ss.index(pair) == len(ss)-1:
                    io.write_err("\n")

    def print_stats(self):
        s  = "Root url : %s\n" % self.root.url
        s += "Web size : %s urls\n" % len(self.index)
        io.write_err(s)

    ### Pickling

    def _to_pickle(self):
        for node in self.index.values():
            for n in node.incoming:
                node.incoming[n] = None
            for n in node.outgoing:
                node.outgoing[n] = None
        #for node in self.index.values():
        #    print node.incoming
        #    print node.outgoing

    def _from_pickle(self):
        for node in self.index.values():
            for n in node.incoming:
                node.incoming[n] = self.index[n]
            for n in node.outgoing:
                node.outgoing[n] = self.index[n]



if __name__ == "__main__":
    (parser, a) = io.init_opts("<web> [options]")
    a("--dump", action="store_true", help="Dump all urls in web")
    a("--in", metavar="<url>", dest="into", help="Find incoming urls to <url>")
    a("--out", metavar="<url>", help="Find outgoing urls from <url>")
    a("--aliases", metavar="<url>", help="Find other urls for the document at <url>")
    a("--multiple", action="store_true", help="Find documents with multiple urls")
    a("--trace", metavar="<url>", help="Trace path from root to <url>")
    a("--deepest", action="store_true", help="Trace url furthest from root")
    a("--popular", action="store_true", help="Find the most referenced urls")
    a("--test", action="store_true", help="Run trace loop test")
    (opts, args) = io.parse_args(parser)
    try:
        if opts.test:
            wb = Web()
            wb.root = Node("a")
            wb.root = Node("a")
            wb.index["a"] = wb.root
            wb.index["b"] = Node("b")
            wb.index["c"] = Node("c")
            #wb.index["b"].incoming["a"] = wb.root      # cut link from a to b
            wb.index["b"].incoming["c"] = wb.index["c"] # create loop b <-> c
            wb.index["c"].incoming["b"] = wb.index["b"]
            io.serialize(wb, "web")
            wb = io.deserialize("web")
            print "Root :", wb.root.url
            print "Index:", wb.index
            print "b.in :", wb.index['b'].incoming
            print "c.in :", wb.index['c'].incoming
            wb.print_trace(wb.get_trace("c"))   # inf loop if loop not detected
            sys.exit()

        conn = sqlite3.connect(args[0])
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        wb = Web(existing=True)
        if opts.dump:
            wb.dump()
        elif opts.into or opts.out:
            wb.print_refs((opts.into or opts.out), opts.out)
        elif opts.aliases:
            wb.print_aliases(opts.aliases)
        elif opts.multiple:
            wb.print_multiple()
        elif opts.trace:
            wb.print_trace(wb.get_trace(opts.trace))
        elif opts.deepest:
            wb.print_trace(wb.deepest_url())
        elif opts.popular:
            wb.print_popular()
        else:
            wb.print_stats()
    except IndexError:
        io.opts_help(None, None, None, parser)
