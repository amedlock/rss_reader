from sqlite3 import *
import sys
from io import StringIO
from os.path import exists, isfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, parse_qsl
from datetime import datetime
from threading import Timer
import webbrowser
from rss import *
import string
import json


rss_view = None


class RSSView(object):
  def __init__(self, fname="feed.db"):
    self.fdb = FeedDB(fname)
    self.feed_config = self.fdb.load_feed_config()
    self.html_template = None
    with open("template.html", 'r') as t:
      self.html_template = Template( t.read() )



class Template(string.Template):
  delimiter="@@"


def show_feeds( cfg, dest, type="Unread" ):
  dest.write("<tbody>")
  if not cfg.feeds:
    dest.write("<tr><td><span class='bold'>No Feeds Defined</span></td></tr></tbody>")
    return
  for f in cfg.feeds:
    n = f.count( type )
    if n<1:
      dest.write("<tr><td colspan='3'>No Items found</td></tr>")
    else:
      for it in f.filter( type ):
        dest.write("<tr>")
        link = "<a href='{0}' target='_blank'>{1}</a>".format( it.link, it.title )
        btn = "<button class='pure-button button-success'>Read</button>"
        dest.write("<td>{0}</td><td>{1}</td><td>{2}</td></td>\n".format( f.name, btn, link ))
        dest.write("</tr>")
  dest.write("</tbody>")

def to_json( feed_cfg ):
  result =[]
  for f in feed_cfg.feeds:
    result.append( {"id":f.id, "name": f.name, "url": f.url, "total": len(f.items), "showUnread":  f.show_unread } )
  return json.dumps( result )

def to_json_item( feed_id, fi ):
  return { "id":fi.id, "feed_id":feed_id, "title":fi.title, "link":fi.link, "read":fi.read }
  


class RSSHandler(BaseHTTPRequestHandler):
  def parse_path(self):
    path = urlparse( self.path ).path
    result = [x.strip("/") for x in path.split("/")]
    return [x for x in result if x]

  def parse_params(self):
    return parse_qs( urlparse(self.path).query)

  def do_GET(self):
    path = self.parse_path()
    if path==["feed"]:
      self.send_response(200)
      self.send_header("Content-type", "text/json; charset=utf-8")
      self.end_headers()
      self.wfile.write( to_json( rss_view.feed_config ).encode("utf-8") )
      return
    if path==["items"]:
      self.send_response(200)      
      self.send_header("Content-type", "text/json; charset=utf-8")
      self.end_headers()      
      args = self.parse_params()
      result = []
      fid = 0
      if args.get("id"):
        fid = int( args['id'][0] )
      for f in rss_view.feed_config.feeds:
        if f.id==fid:
          result = f.items
      self.wfile.write( json.dumps( [ to_json_item(fid,it) for it in result] ).encode("utf-8") )
      return
    # default response
    self.send_response(200)
    self.send_header("Content-type", "text/html; charset=utf-8")
    self.end_headers()
    html = rss_view.html_template.substitute( { "serverUrl":'http://localhost:8000' } )
    self.wfile.write( html.encode("utf-8") )

  def parse_form(self):
    length = int(self.headers.get('content-length'))
    field_data = self.rfile.read(length).decode('utf-8')
    return dict(x for x in parse_qsl(field_data))

  def do_POST(self):
    args = self.parse_form()
    path = self.parse_path()
    if path==["mark"]:
      id = int( args.get("id", "0"))
      val = args.get("read", "false")=="true"
      rss_view.feed_config.mark( id, val )
      self.send_response(200);
      self.send_header("Content-type", "text/html; charset=utf-8")
      self.end_headers()
      self.wfile.write(''.encode('utf-8'))
    if path==["refresh"]:
      pass # todo



  def get_feed(self):
    args = self.parse_params()
    t = args.get("filter", "All")
    self.send_response(200)
    self.send_header("Content-type", "text/html; charset=utf-8")
    self.end_headers()
    result = StringIO()
    show_feeds( rss_view.feed_config, result, t )
    self.wfile.write( result.getvalue().encode("utf-8") )

  def get_jquery(self):
    self.send_response(200)
    self.send_header("Content-type", "text/html; charset=utf-8")
    self.end_headers()
    with open(self.path[1:],'r') as jq:
      self.wfile.write( jq.read().encode('utf-8'))


if __name__ == "__main__":
  if not exists("feed.db") and isfile("feed.db"):
    print("RSS database not found!  Aborting.")
    sys.exit(-1)

  rss_view = RSSView("feed.db")

  Timer(2.0, lambda: webbrowser.open( "http://localhost:8000") ).start()
  try:
    server_address = ('', 8000)
    httpd = HTTPServer( server_address, RSSHandler )
    print("RSS Server started on port: {0}".format( server_address[1] ))
    httpd.serve_forever()
  except KeyboardInterrupt:
    pass

  httpd.server_close()
  print("RSS Server stopped")







