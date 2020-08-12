"""Serve OSTree on local network
"""

import logging
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, HTTPServer

class TCBuilderHTTPRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler which makes use of logging framework"""
    def __init__(self, *args, **kwargs):
        self.log = logging.getLogger("torizon." + __name__)
        super().__init__(*args, **kwargs)

    #pylint: disable=redefined-builtin,logging-not-lazy
    def log_message(self, format, *args):
        self.log.debug(format % args)

class HTTPThread(threading.Thread):
    """HTTP Server thread"""
    def __init__(self, directory):
        threading.Thread.__init__(self, daemon=True)

        self.log = logging.getLogger("torizon." + __name__)
        self.log.info("Starting http server to serve OSTree.")

        # From what I understand, this creates a __init__ funciton with the
        # directory argument already set. Nice hack!
        handler_init = partial(TCBuilderHTTPRequestHandler, directory=directory)
        self.http_server = HTTPServer(("", 8080), handler_init)

    def run(self):
        self.http_server.serve_forever()

    def shutdown(self):
        """Shutdown HTTP server"""
        self.log.debug("Shutting down http server.")
        self.http_server.shutdown()

def serve_ostree_start(ostree_dir):
    """Serving given path via http"""
    http_thread = HTTPThread(ostree_dir)
    http_thread.start()
    return http_thread

def serve_ostree_stop(http_thread):
    """Stop serving"""
    http_thread.shutdown()
