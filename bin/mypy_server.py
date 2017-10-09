#!/usr/bin/env python
# coding=utf-8
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

import re
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Set  # noqa

import hashlib
import io
import json
import multiprocessing
import os
import time
import shlex
from subprocess import Popen, PIPE
from threading import Condition
import sys
from Queue import Queue

from findimports import ModuleGraph
from findimports import Module  # noqa
from watchdog.events import FileModifiedEvent
from watchdog.events import FileSystemEvent     # noqa
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer
from watchdog.utils import BaseThread

from mypytools.config import config


STRICT_OPTIONAL_DIRS = [os.path.join(config['root_dir'], d['path']) for d in config['src_dirs'] if d.get('strict_optional')]

T = TypeVar('T')


def print_divider(text=None, newline_before=False):
    # type: (Optional[str], bool) -> None
    if text is None:
        text = ''
    width = 80
    num_stars = width - len(text)
    if num_stars < 0:
        num_stars = 0
    num_left_stars = num_stars // 2
    num_right_stars = num_stars - num_left_stars
    newline = '\n' if newline_before else ''
    print('{}{}{}{}'.format(newline, '*' * num_left_stars, text, '*' * num_right_stars))


class MypyQueueingHandler(PatternMatchingEventHandler):
    patterns = ['*.py']

    def __init__(self):
        # type: () -> None
        self.events = Queue()       # type: Queue[FileSystemEvent]
        self.last_deleted = None    # type: Optional[str]
        self.event_handler = None   # type: Optional[MypyEventHandler]
        super(MypyQueueingHandler, self).__init__()

    def _notify_event_handler(self):
        # type: () -> None
        if self.event_handler is None:
            return
        self.event_handler.task_cond.acquire()
        self.event_handler.task_cond.notify_all()
        self.event_handler.task_cond.release()

    def on_deleted(self, event):
        # type: (FileSystemEvent) -> None
        self.last_deleted = event.src_path
        self.events.put(event)
        self._notify_event_handler()

    def on_created(self, event):
        # type: (FileSystemEvent) -> None
        self.events.put(event)
        self._notify_event_handler()
        if event.src_path == self.last_deleted:
            self.on_modified(FileModifiedEvent(event.src_path))

    def on_modified(self, event):
        # type: (FileSystemEvent) -> None
        self.events.put(event)
        self._notify_event_handler()

    @property
    def has_new_events(self):
        # type: () -> bool
        return not self.events.empty()

    def next_event(self, receiver):
        # type: (MypyEventHandler) -> None
        while True:
            # If there aren't any items in the queue, block until there is.
            event = self.events.get(block=True)
            # If that was the last item, that's the one we want.
            if self.events.qsize() == 0:
                break
        assert event is not None

        if event.event_type == 'deleted':
            receiver.on_deleted(event)
        elif event.event_type == 'created':
            receiver.on_created(event)
        elif event.event_type == 'modified':
            receiver.on_modified(event)
        else:
            print('Unknown event type: {}'.format(event.event_type))


class MypyWorker(BaseThread):
    def __init__(self, task_pool, task_cond, file_cache):
        # type: (List[MypyTask], Condition, MypyFileCache) -> None
        self._task_pool = task_pool
        self._task_cond = task_cond
        self.run_tasks = False
        self.current_task = None    # type: Optional[MypyTask]
        self.file_cache = file_cache
        super(MypyWorker, self).__init__()

    def run(self):
        # type: () -> None
        while True:
            self._run_next_task()

    def _run_next_task(self):
        # type: () -> None
        self._task_cond.acquire()
        while len(self._task_pool) == 0 or not self.run_tasks:
            self._task_cond.wait()
        self.current_task = self._task_pool.pop(0)
        self._task_cond.release()

        output, file_hash = self.current_task.execute()

        self._task_cond.acquire()
        self.file_cache.store(self.current_task.filename, file_hash, output)
        self.current_task = None
        if len(output) > 0:
            sys.stdout.write(output)
            sys.stdout.flush()
        self._task_cond.notify_all()
        self._task_cond.release()


class MypyTask(object):
    def __init__(self, filename):
        # type: (str) -> None
        self.filename = filename
        self._proc = None   # type: Optional[Popen]

    def _should_use_strict_optional(self, path):
        # type: (str) -> bool
        for strict_path in STRICT_OPTIONAL_DIRS:
            if path.startswith(strict_path):
                return True
        return False

    def _get_file_hash(self):
        # type: () -> str
        with open(self.filename, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def execute(self):
        # type: () -> Tuple[str, str]
        mypy_path = os.pathsep.join(os.path.join(config['root_dir'], path) for path in config.get('mypy_path', []))
        strict_optional = '--strict-optional' if self._should_use_strict_optional(self.filename) else ''
        cmd = shlex.split(
            "/usr/local/bin/mypy --py2 --ignore-missing-imports --follow-imports=silent {} {}".format(strict_optional,
                                                                                                      self.filename))
        try:
            before_file_hash = self._get_file_hash()
            after_file_hash = ''
            out = ''
            exit_code = 0
            while before_file_hash != after_file_hash:
                before_file_hash = after_file_hash
                self._proc = Popen(cmd, stdout=PIPE, stderr=PIPE, env={'MYPY_PATH': mypy_path})
                out, err = self._proc.communicate()
                exit_code = self._proc.wait()
                # This still has an ABA problem, but ¯\_(ツ)_/¯
                after_file_hash = self._get_file_hash()
            return ('', before_file_hash) if exit_code == 0 else (out, before_file_hash)
        except Exception as e:
            print(e)
            return '', ''
        finally:
            self._proc = None

    def interrupt(self):
        # type: () -> None
        if self._proc is None:
            return
        try:
            # There's a race between interrupting the stored process and
            # the process exiting. If the process exits first then killing
            # it will throw an OSError, so just swallow that and keep going.
            self._proc.kill()
        except OSError:
            pass

    def __eq__(self, other):
        # type: (object) -> bool
        if not isinstance(other, MypyTask):
            raise NotImplemented
        return self.filename == other.filename

    def __hash__(self):
        # type: () -> int
        return self.filename.__hash__()


class MypyFileCache(object):
    def __init__(self):
        # type: () -> None
        self._cache = {}    # type: Dict[str, Tuple[str, str]]

    def lookup(self, filename_hash, file_hash):
        # type: (str, int) -> Optional[str]
        result = self._cache.get(filename_hash)
        if result is None:
            return None
        if result[0] != file_hash:
            return None
        return result[1]

    def store(self, filename, file_hash, output):
        # type: (str, str, str) -> None
        self._cache[hashlib.md5(filename).hexdigest()] = (file_hash, output)


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
        self.wfile.write(json.dumps({'output': output}))

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


class MypyEventHandler(BaseThread):
    def __init__(self, dep_graph, queueing_handler, file_cache):
        # type: (ModuleGraph, MypyQueueingHandler, MypyFileCache) -> None
        self.dep_graph = dep_graph
        self.worker_pool = []   # type: List[MypyWorker]
        self.task_pool = []     # type: List[MypyTask]
        self.task_cond = Condition()
        self.queueing_handler = queueing_handler
        self.file_cache = file_cache
        super(MypyEventHandler, self).__init__()

    def on_deleted(self, event):
        # type: (FileSystemEvent) -> None
        pass

    def on_created(self, event):
        # type: (FileSystemEvent) -> None
        pass

    def _add_task(self, task, index=None):
        # type: (MypyTask, Optional[int]) -> None
        if task in self.task_pool:
            return
        if index is None:
            self.task_pool.append(task)
        else:
            self.task_pool.insert(index, task)

    def _find_modified_module(self, src_path):
        # type: (str) -> Optional[Module]
        modified_module = None
        for module_ in self.dep_graph.listModules():
            if module_.filename == src_path:
                modified_module = module_
                break
        return modified_module

    def _find_dependencies(self, root_module):
        # type: (Module) -> Set[str]
        modified_modules = {root_module}
        dependencies_to_check = set()

        def check_module(mod):
            # type: (Module) -> None
            # If it's an __init__ file then we might have changed the interface to
            # this module, so add it to the set of modified modules. This will cause
            # us to iterate all modules again.
            if mod.modname.endswith('__init__'):
                modified_modules.add(mod)
            else:
                dependencies_to_check.add(os.path.abspath(mod.filename))

        while True:
            modified_modules_size = len(modified_modules)

            for module_ in self.dep_graph.listModules():
                for import_name in module_.imports:
                    modified_modnames = {mod.modname for mod in modified_modules}

                    if import_name in modified_modnames:
                        check_module(module_)
                        break

                    elif '{}.__init__'.format(import_name) in modified_modnames:
                        check_module(module_)
                        break

            # Run until we haven't added any new modules to the set of modified modules.
            # We do this to catch the following cases:
            # (1) an init exports another init's methods (uncommon)
            # (2) we have a.py (modified) <- __init__.py <- b.py and we happen to scan b.py first (more common)
            if modified_modules_size == len(modified_modules):
                break

        dependencies_to_check.update({os.path.abspath(module_.filename) for module_ in modified_modules})
        return dependencies_to_check

    def _ensure_workers(self):
        # type: () -> None
        while len(self.worker_pool) < multiprocessing.cpu_count():
            worker = MypyWorker(self.task_pool, self.task_cond, self.file_cache)
            self.worker_pool.append(worker)
            worker.start()

    def _disable_workers(self):
        # type: () -> None
        # Prevent workers from consuming any tasks in the queue until we're ready.
        for worker in self.worker_pool:
            worker.run_tasks = False

    def _enable_workers(self):
        # type: () -> None
        # Mark all workers to start running tasks and interrupt any
        # workers with tasks that will need to be re-run.
        for worker in self.worker_pool:
            worker.run_tasks = True
            if worker.current_task is None:
                continue
            if worker.current_task in self.task_pool:
                worker.current_task.interrupt()
        self.task_cond.notify_all()

    def _wait_until_tasks_completed(self):
        # type: () -> None
        start_size = len(self.task_pool)
        while len(self.task_pool) > 0 and not self.queueing_handler.has_new_events:
            curr_size = len(self.task_pool)
            total_completed_tasks = start_size - curr_size
            sys.stdout.write('  {}/{}\r'.format(total_completed_tasks, start_size))
            sys.stdout.flush()
            self.task_cond.wait()

        if self.queueing_handler.has_new_events:
            print('Detected new changes, interrupting...')
        else:
            # Even though all tasks have been pulled from the task_pool,
            # they might not have been completed, so we have to wait until all
            # workers have cleared their current_task field.
            all_clear = False
            while not all_clear:
                all_clear = True
                for worker in self.worker_pool:
                    if worker.current_task is not None:
                        all_clear = False
                        break
                if not all_clear:
                    self.task_cond.wait()

    def on_modified(self, event):
        # type: (FileSystemEvent) -> None
        print_divider('TYPECHECKING', newline_before=True)

        modified_module = self._find_modified_module(event.src_path)
        if modified_module is None:
            print('Unable to find module for modified file {}'.format(event.src_path))
            print_divider('DONE')
            return

        dependencies_to_check = self._find_dependencies(modified_module)

        self.task_cond.acquire()

        # Add the modified file first so it's the first one to be checked.
        self._add_task(MypyTask(os.path.abspath(modified_module.filename)), index=0)
        for filename in dependencies_to_check:
            self._add_task(MypyTask(filename))

        self._ensure_workers()
        self._enable_workers()
        self._wait_until_tasks_completed()
        self._disable_workers()

        print_divider('DONE')
        self.task_cond.release()

    def run(self):
        while True:
            self.queueing_handler.next_event(self)


def run_mypy_server():
    # type: () -> None
    src_dirs = [os.path.join(config['root_dir'], d['path']) for d in config.get('src_dirs', [])]

    sys.stdout.write("Initializing mypy server...")
    sys.stdout.flush()

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.BytesIO()
    sys.stderr = io.BytesIO()

    try:
        g = ModuleGraph()
        for d in src_dirs:
            g.parsePathname(d)
        g.external_dependencies = False
        g.trackUnusedNames = True
    except Exception:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

        g = ModuleGraph()
        for d in src_dirs:
            g.parsePathname(d)
        g.external_dependencies = False
        g.trackUnusedNames = True

    sys.stdout = old_stdout
    sys.stderr = old_stderr

    sys.stdout.write("Done!\n")
    sys.stdout.flush()

    file_cache = MypyFileCache()

    queueing_handler = MypyQueueingHandler()
    mypy_handler = MypyEventHandler(g, queueing_handler, file_cache)
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


if __name__ == "__main__":
    run_mypy_server()
