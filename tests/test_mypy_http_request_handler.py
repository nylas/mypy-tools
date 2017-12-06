import sys

from typing import Any, Type, Tuple, Union

try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock   # type: ignore

if sys.version_info[0] > 2:
    from http.server import BaseHTTPRequestHandler, HTTPServer
else:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

from mypytools.server.mypy_http_request_handler import MypyHttpRequestHandler

try:
    # Python 2.x
    import BaseHTTPServer as server
    from StringIO import StringIO as IO
except ImportError:
    # Python 3.x
    from http import server
    from io import BytesIO as IO


class IOProxy(object):
    def __init__(self):
        # type: () -> None
        self.copy = IO()
        self.stream = IO()

    def write(self, stuff):
        # type: (Union[str, bytes]) -> None
        self.copy.write(stuff)
        self.stream.write(stuff)

    def flush(self):
        # type: () -> None
        self.copy.flush()
        self.stream.flush()

    def close(self):
        # type: () -> None
        self.stream.close()

    def closed(self):
        # type: () -> None
        return self.stream.closed


class MockRequest(object):
    def __init__(self, path):
        # type: (str) -> None
        self.path = path
        self.body = IOProxy()

    def makefile(self, flags, *args, **kwargs):
        # type: (str, *Any, **Any) -> Union[IO, IOProxy]
        if flags.startswith('w'):
            return self.body

        if sys.version_info[0] > 2:
            output = bytes("GET {}".format(self.path), 'ascii')
        else:
            output = "GET {}".format(self.path)
        return IO(output)

    def sendall(self, b):
        self.body.write(b)


class MockServer(object):
    def __init__(self, ip_port, handler_cls, file_cache, path):
        # type: (Tuple[str, int], Type[BaseHTTPRequestHandler], Any, str) -> None
        self.file_cache = file_cache
        self.active_request = MockRequest(path)
        handler = handler_cls(self.active_request, ip_port, self)   # type: ignore


def test_http_request_handler():
    # type: () -> None
    file_cache = Mock()
    file_cache.lookup.side_effect = [None, 'Error on line 2']
    paths = [
        ('/', b''),
        ('/file/f00/ba12', b''),
        ('/file/f00/ba12ba2', b'{"output": "Error on line 2"}')
    ]
    for path, expected in paths:
        server = MockServer(('0.0.0.0', 8888), MypyHttpRequestHandler, file_cache, path)
        assert expected == server.active_request.body.copy.getvalue()
