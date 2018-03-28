#!/usr/bin/env python
# coding=utf-8
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from typing import List  # noqa

import io
import os
import time
import sys

from findimports import ModuleGraph
from watchdog.observers import Observer

from mypytools.config import config
from mypytools.server.mypy_event_handler import MypyEventHandler
from mypytools.server.mypy_file_cache import MypyFileCache
from mypytools.server.mypy_http_request_handler import HttpServerThread
from mypytools.server.mypy_queueing_handler import MypyQueueingHandler


def build_dependency_graph(src_dirs, silence):
    # type: (List[str], bool) -> ModuleGraph
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    if silence:
        sys.stdout = io.StringIO()  # type: ignore
        sys.stderr = io.StringIO()  # type: ignore

    try:
        g = ModuleGraph()
        for d in src_dirs:
            g.parsePathname(d)
        g.external_dependencies = False
        g.trackUnusedNames = True
        return g
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def run_server(compact, num_workers):
    # type: (bool, int) -> None
    src_dirs = [os.path.join(config['root_dir'], d['path']) for d in config.get('src_dirs', [])]

    sys.stdout.write("Initializing mypy server with {} workers...".format(num_workers))
    sys.stdout.flush()

    try:
        g = build_dependency_graph(src_dirs, silence=True)
    except Exception:
        g = build_dependency_graph(src_dirs, silence=False)

    sys.stdout.write("Done!\n")
    sys.stdout.flush()

    file_cache = MypyFileCache()

    queueing_handler = MypyQueueingHandler(src_dirs)
    mypy_handler = MypyEventHandler(g, queueing_handler, file_cache, compact, num_workers)
    queueing_handler.event_handler = mypy_handler
    mypy_handler.start()

    http_server_thread = HttpServerThread(file_cache)
    http_server_thread.start()

    observer = Observer()
    observer.schedule(queueing_handler, path=config['root_dir'], recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()

