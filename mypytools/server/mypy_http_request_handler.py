from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import json
import sys
import re
from typing import Any

from watchdog.utils import BaseThread

from mypytools.config import config
from mypytools.server.mypy_file_cache import MypyFileCache

if sys.version_info[0] > 2:
    from http.server import BaseHTTPRequestHandler, HTTPServer
else:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


class MypyHttpRequestHandler(BaseHTTPRequestHandler):
    file_path_regex = re.compile(r'^/file/([0-9a-f]+)/([0-9a-f]+)$')

    def _set_headers(self, response_code):
        # type: (int) -> None
        self.send_response(response_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        # type: () -> None
        result = self.file_path_regex.match(self.path)
        if result is None:
            self._set_headers(response_code=404)
            return

        file_name_hash = result.group(1)
        file_content_hash = result.group(2)
        file_cache = self.server.file_cache     # type: ignore
        output = file_cache.lookup(file_name_hash, file_content_hash)

        if output is None:
            self._set_headers(response_code=404)
            return

        self._set_headers(response_code=200)
        output = json.dumps({'output': output})
        if sys.version_info[0] > 2:
            output = bytes(output, encoding='utf-8')
        self.wfile.write(output)

    def log_message(self, format, *args):
        # type: (str, *Any) -> None
        return


class HttpServerThread(BaseThread):
    def __init__(self, file_cache):
        # type: (MypyFileCache) -> None
        self.file_cache = file_cache
        super(HttpServerThread, self).__init__()

    def run(self):
        # type: () -> None
        server_address = ('127.0.0.1', config['port'])
        httpd = HTTPServer(server_address, MypyHttpRequestHandler)
        httpd.file_cache = self.file_cache  # type: ignore
        httpd.serve_forever()

