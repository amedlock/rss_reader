import sys, re, time
from datetime import datetime
from os.path import isfile, isdir, exists
from xml.dom import minidom
from urllib.request import *
from urllib.error import HTTPError
import sqlite3


# Helper functions for XML
def header( r, name ):
  if r and (name in r.headers):
    return r.headers[name]
  else:
    return None

def find(elem, name):
  result = elem.getElementsByTagName(name) if elem else []
  return result[0] if result else None
  
def each(elem,name):
  return elem.getElementsByTagName(name) if elem else []

def attr(elem, name): 
  return elem.getAttribute(name) if elem.hasAttribute(name) else ''

def text(elem):
  if not elem: return ''
  elif elem.nodeType == minidom.Node.TEXT_NODE:
    return elem.data
  elif elem.nodeType == minidom.Node.ELEMENT_NODE:
    ch = filter( None, [text(x) for x in elem.childNodes] )
    return ''.join( ch )
  else:
    return ''


# Feed data classes
class FeedConfig(object):
  """ Basic container Feed objects """
  def __init__(self):
    self.feeds = []

  def mark(self, id, val):
    for f in self.feeds:
      for it in f.items:
        if it.id==id:
          it.read = val
          save_feed_item( f, it, db )
          return True
    return False

  def add_feed( self, f ):
    self.feeds.append( f )


class FeedItem(object):
  def __init__(self, title, link, desc, id=None, read=False ):
    self.title = title
    self.link = link
    self.desc = desc
    self.id = id
    self.read = read in ["True", True, "true"]

  def __str__(self): return "({0} '{1}')".format(self.title, self.link)



class Feed(object):
  def __init__(self, name, url, **args ):
    self.id = args.get("id", None)
    self.name= name
    self.url= url
    self.desc = args.get("desc", None)
    self.encoding = args.get('encoding','utf-8')
    self.last_updated = args.get("last_updated", None)
    self.etag = args.get( "etag", None )
    self.xml = None
    self.items = []
    self.show_unread = args.get("show_unread", False ) in [True, "true"]
    self.logs = []

  def __str__(self): return "({0}:{1}, {2} items)".format( self.name, self.url, len(self.items))

  def count(self, t="All"):
    return len( self.filter(t) )

  def filter(self, t):
    if t.lower()=="unread": return [x for x in self.items if not x.read]
    elif t.lower()=="read": return [x for x in self.items if x.read]
    else: return self.items

  def add_item( self, fi ):
    self.items.append( fi )

  def add_log( self, txt ):
    self.logs.append( txt )


# Sqlite database interface
class FeedDB(object):
  tables = {
    "rss_feed":"create table rss_feed(id integer primary key asc, name, url, desc, show_unread, last_updated, etag);", 
    "rss_xml":"create table rss_xml(feed_id integer, xml, tstamp);" ,
    "rss_item": "create table rss_item(id integer primary key asc, feed_id, title, link, desc, read );",
    "rss_log":"CREATE TABLE rss_log(id integer primary key asc, feed_id, tstamp, status, text);"
  }
  def __init__(self, fname="feed.db"):
    self.con = sqlite3.connect(fname)
    self.setup_db()

  def table_missing( self, cur, table_name ):
    cur.execute("select * from sqlite_master where type=? and name=?", ( 'table', table_name))
    return cur.fetchone() == None

  def setup_db(self):
    cur = self.con.cursor()
    missing = [ddl for (table,ddl) in self.tables.items() if self.table_missing(cur, table)]
    for ddl in missing:
      cur.execute(ddl)
    self.con.commit()

  def load_feed_items(self, feed):
    sql = "select id, title, link, desc, read from rss_item where feed_id = ?"
    for (id, title, link, desc, is_read) in self.con.execute( sql , (feed.id,) ):
      fi = FeedItem( title, link,desc, id, is_read )
      feed.add_item( fi )

  def load_feed_config(self):
    result = FeedConfig()
    sql = "select id, name, url, desc, show_unread, last_updated, etag from rss_feed"
    for (id, name, url, desc, show_unread, last_updated, etag) in self.con.execute(sql):
      f = Feed(name, url, desc=desc, last_updated=last_updated, etag=etag, id=id, show_unread=show_unread)
      result.add_feed( f )
      self.load_feed_items( f )
    return result

  def save_feed_item( self, feed, item ):
    """ Feed Items don't change, so just insert if necessary """
    cur = self.con.cursor()
    if not item.id:
      title = item.title if item.title else "None"
      link = item.link if item.link else "#"
      desc = item.desc or title 
      cur.execute("insert into rss_item(feed_id, title, link, desc) values (?, ?, ?, ? );", (feed.id, title, link, desc ))
      item.id = cur.lastrowid
    else:
      val = "true" if item.read else "false"
      cur.execute("update rss_item set read=? where id = ?", (val , item.id))
    self.con.commit()

  def save_feed( self, feed ):
      """ Save a Feed to the database, or update if any items changed """
      now = datetime.now()
      tstamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
      cur = self.con.cursor()
      if feed.id:
        cur.execute("update rss_feed set last_updated=?, etag=? where id=?", (feed.last_updated, feed.etag, feed.id))
      else:
        cur.execute("insert into rss_feed(name, url, desc, last_updated, etag) values(?, ?, ?, ?, ?)",
          (feed.name, feed.url, feed.desc, str(feed.last_updated), feed.etag ) )
        feed.id = cur.lastrowid  
      self.con.commit()
      for it in feed.items:
        self.save_feed_item( feed, it )
      for it in feed.logs:
        cur.execute("insert into rss_log( feed_id, status, text, tstamp) values( ?, 'INFO', ?, ?)", (feed.id, it, tstamp))
      feed.logs= []
      if feed.xml:
        cur.execute("insert into rss_xml( feed_id, xml, tstamp) values (?,?,?)", (feed.id, feed.xml, tstamp))
        feed.xml = None
      self.con.commit()

  def save_feed_config( self,feed_config ):
    for feed in feed_config.feeds:
      self.save_feed( feed )



# All parsing of RDF/Atom XML into Feed/FeedInfo/FeedItem objects

def atom_parse( root , feed ):
  for elem in each( root, "entry" ):
    title = text( find(elem, "title"))
    link = attr( find(elem, "link"), "href")
    feed.add_item( FeedItem(title, link, title, None, False ) )
  
def rdf_parse( root, feed ):
  for elem in each( root, "item"):
    title = text( find(elem, 'title') ) 
    link = text( find(elem, 'link') )
    desc = text( find( elem, 'description') )
    feed.add_item( FeedItem(title, link, desc, None, False))

def parse_rss( xml, feed ):
  doc = minidom.parseString( xml )
  root = doc.documentElement
  if root.tagName=='feed':
    atom_parse( root, feed )
  elif root.tagName.lower() in ['rss','rdf', 'rdf:rdf']:
    rdf_parse( root, feed )
  else:
    raise Exception("Unknown RSS format, root:{0}".format( root.tagName ))

#  Reading of XML from RSS endpoints

def decode(content):
  if not content: 
    return ''
  try:
    return content.decode('utf-8')
  except UnicodeDecodeError as e:
    return content.decode('iso-8859-1')

import traceback

def load_feed(feed):
  req = Request(url=feed.url, method='GET' )
  req.add_header("User-agent", "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0")
  if feed.last_updated:
    req.add_header("If-Modified-Since", feed.last_updated)
  if feed.etag:
    req.add_header("If-None-Match", feed.etag)
  try:
    with urlopen(req) as f:
      result = decode( f.read() )
      feed.xml = result
      lastmod = header( f, "Last-Modified") or header(f, "Date") 
      if lastmod:
        feed.last_updated = lastmod
      etag = header(f, "ETag")
      if etag:
        feed.etag = etag
      parse_rss( result, feed )
      print("Loaded rss items from {0}".format( feed.name ))
  except HTTPError as he:
    if he.code==304:  
      feed.add_log("No New items found")
    else:
      feed.add_log("Error reading feed {0} ({1} {2})".format(feed.name, he.code, he.reason ))
  except Exception as err:
    feed.add_log("Could not read feed {0} at:{1}\n Error:{2}".format( feed.name, feed.url, err ))
    traceback.print_exc()





#  for importing RSS Feed info from Digg XML Export
def parse_digg_config(loc):
  result = FeedConfig()
  doc = minidom.parse( loc )
  root = doc.documentElement
  folder = None
  for elem in each(root, "outline"):
    xmlUrl = attr( elem, "xmlUrl")
    title = attr(elem, "title")
    if title and not xmlUrl:
      folder = title
    else:
      desc = attr(elem, "text")
      result.add_feed( Feed(desc, xmlUrl) )
  return result


if __name__ == "__main__":
  fdb = FeedDB('feed.db')
  feed_config = fdb.load_feed_config()

  cmd = sys.argv[1].lower() if len(sys.argv)>1 else ''

  if cmd=='show':
    print("**** Feeds in database ****")
    for f in feed_config.feeds:
      print( str(f) )

  if cmd=="import":
    if exists( "digg.xml") and isfile("digg.xml"):
      digg = parse_digg_config("d:/proj/rss/digg.xml")
      fdb.save_feed_config( digg )
    
  if cmd=='refresh':
    for f in feed_config.feeds:
      load_feed(f)
      for it in f.logs: 
        print("{0}:{1}".format( f.name, it) )
      fdb.save_feed(f)


