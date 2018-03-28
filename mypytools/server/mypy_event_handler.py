from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from threading import Condition
import os
import sys

from findimports import ModuleGraph, Module
from typing import List, Optional, Set, TYPE_CHECKING
from watchdog.events import FileSystemEvent
from watchdog.utils import BaseThread

from mypytools.server.mypy_task import MypyTask
from mypytools.server.mypy_worker import MypyWorker
if TYPE_CHECKING:
    from mypytools.server.mypy_file_cache import MypyFileCache
    from mypytools.server.mypy_queueing_handler import MypyQueueingHandler


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


class MypyEventHandler(BaseThread):
    def __init__(self, dep_graph, queueing_handler, file_cache, compact, num_workers):
        # type: (ModuleGraph, MypyQueueingHandler, MypyFileCache, bool, int) -> None
        self.dep_graph = dep_graph
        self.worker_pool = []   # type: List[MypyWorker]
        self.task_pool = []     # type: List[MypyTask]
        self.task_cond = Condition()
        self.queueing_handler = queueing_handler
        self.file_cache = file_cache
        self.compact = compact
        self.num_workers = num_workers
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
        while len(self.worker_pool) < self.num_workers:
            worker = MypyWorker(self.task_pool, self.task_cond, self.file_cache, self.compact)
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

        self.task_cond.acquire()

        modified_module = self._find_modified_module(event.src_path)
        if modified_module is None:
            print('Unable to find module for modified file {}'.format(event.src_path))
            dependencies_to_check = {event.src_path}
        else:
            dependencies_to_check = self._find_dependencies(modified_module)

            # Add the modified file first so it's the first one to be checked.
            self._add_task(MypyTask(os.path.abspath(modified_module.filename)),index=0)

        for filename in dependencies_to_check:
            self._add_task(MypyTask(filename))

        self._ensure_workers()
        self._enable_workers()
        self._wait_until_tasks_completed()
        self._disable_workers()

        print_divider('DONE')
        self.task_cond.release()

    def run(self):
        # type: () -> None
        while True:
            self.queueing_handler.next_event(self)

