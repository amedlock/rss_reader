# rss_reader
Very basic RSS reader in python, not finished but (somewhat) working

RSS reader in python and VueJS 2.
The rss.py file has the following commands:

__python rss.py import__

This it will import a file called "digg.xml" which must be an OPML file

__python rss.py refresh__

This attempts to load new items from your feeds, uses Last-Modified and ETags to only pull new items.

__python server.py__

This starts up the webserver and shows your feeds in a browser window.

Don't know when/if I will finish this.  Several dumb design choices but it was thrown together in about 5 hours total.
