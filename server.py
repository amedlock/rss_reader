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

if not exists("feed.db") and isfile("feed.db"):
  print("RSS database not found!  Aborting.")
  sys.exit(-1)

db = sqlite3.connect("feed.db")

feed_config = load_feed_config( db )

class Template(string.Template):
  delimiter="@@"

with open("template.html", 'r') as t:
  html_template = Template( t.read() )

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
  def do_GET(self):
    if self.path.startswith("/jquery"):
      self.get_jquery()
      return
    if self.path.startswith("/feed"):
      self.send_response(200)
      self.send_header("Content-type", "text/json; charset=utf-8")
      self.end_headers()
      self.wfile.write( to_json( feed_config ).encode("utf-8") )
      return
    if self.path.startswith("/items"):
      self.send_response(200)      
      self.send_header("Content-type", "text/json; charset=utf-8")
      self.end_headers()      
      args = self.parse_params()
      result = []
      fid = 0
      if args.get("id"):
        fid = int( args['id'][0] )
      for f in feed_config.feeds:
        if f.id==fid:
          result = f.items
      self.wfile.write( json.dumps( [ to_json_item(fid,it) for it in result] ).encode("utf-8") )
      return
    # default response
    self.send_response(200)
    self.send_header("Content-type", "text/html; charset=utf-8")
    self.end_headers()
    html = html_template.substitute( { "serverUrl":'http://localhost:8000' } )
    self.wfile.write( html.encode("utf-8") )

  def parse_form(self):
    length = int(self.headers.get('content-length'))
    field_data = self.rfile.read(length).decode('utf-8')
    return dict(x for x in parse_qsl(field_data))

  def do_POST(self):
    args = self.parse_form()
    if self.path.startswith("/mark"):
      id = int( args.get("id", "0"))
      val = args.get("read", "false")=="true"
      feed_config.mark( id, val )
      self.send_response(200);
      self.send_header("Content-type", "text/html; charset=utf-8")
      self.end_headers()
      self.wfile.write(''.encode('utf-8'))


  def parse_params(self):
    return parse_qs( urlparse(self.path).query)
    #return dict([x.split("=") for x in urlparse(self.path).query.split('&')])

  def get_feed(self):
    args = self.parse_params()
    t = args.get("filter", "All")
    self.send_response(200)
    self.send_header("Content-type", "text/html; charset=utf-8")
    self.end_headers()
    result = StringIO()
    show_feeds( feed_config, result, t )
    self.wfile.write( result.getvalue().encode("utf-8") )

  def get_jquery(self):
    self.send_response(200)
    self.send_header("Content-type", "text/html; charset=utf-8")
    self.end_headers()
    with open(self.path[1:],'r') as jq:
      self.wfile.write( jq.read().encode('utf-8'))


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







