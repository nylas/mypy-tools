from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from threading import Condition
import sys
from typing import List, Optional

from watchdog.utils import BaseThread

from mypytools.server.mypy_file_cache import MypyFileCache
from mypytools.server.mypy_task import MypyTask


class MypyWorker(BaseThread):
    def __init__(self, task_pool, task_cond, file_cache, compact):
        # type: (List[MypyTask], Condition, MypyFileCache, bool) -> None
        self._task_pool = task_pool
        self._task_cond = task_cond
        self.run_tasks = False
        self.current_task = None    # type: Optional[MypyTask]
        self.file_cache = file_cache
        self.compact = compact
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

        exit_code, output, full_context, file_hash = self.current_task.execute()

        self._task_cond.acquire()
        self.file_cache.store(self.current_task.filename, file_hash, output)
        self.current_task = None
        if len(output) > 0:
            if self.compact:
                sys.stdout.write(output)
            else:
                sys.stdout.write(full_context)
            sys.stdout.flush()
        else:
            assert exit_code == 0
        self._task_cond.notify_all()
        self._task_cond.release()

