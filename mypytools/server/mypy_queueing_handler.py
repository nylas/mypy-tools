from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from Queue import Queue
from typing import Optional, List

from watchdog.events import PatternMatchingEventHandler, FileSystemEvent, FileModifiedEvent

from mypytools.server.mypy_event_handler import MypyEventHandler


class MypyQueueingHandler(PatternMatchingEventHandler):
    patterns = ['*']
    ignore_patterns = ['*.swp', '*/.venv/*', '*/venv/*', '*/.mypy_cache/*']
    ignore_directories = True

    def __init__(self, src_dirs):
        # type: (List[str]) -> None
        self.events = Queue()       # type: Queue[FileSystemEvent]
        self.last_deleted = None    # type: Optional[str]
        self.event_handler = None   # type: Optional[MypyEventHandler]
        self.src_dirs = src_dirs
        super(MypyQueueingHandler, self).__init__()

    def _should_check_file(self, path):
        # type: (str) -> bool
        in_src_dir = False
        for src_dir in self.src_dirs:
            if path.startswith(src_dir):
                in_src_dir = True
                break

        if not in_src_dir:
            return False

        if path.endswith('.py'):
            return True
        try:
            with open(path, 'r') as f:
                first_line = f.readline().rstrip('\n')
                if first_line.startswith('#!') and first_line.endswith('python'):
                    return True
        except IOError:
            pass
        return False

    def _notify_event_handler(self):
        # type: () -> None
        if self.event_handler is None:
            return
        self.event_handler.task_cond.acquire()
        self.event_handler.task_cond.notify_all()
        self.event_handler.task_cond.release()

    def on_deleted(self, event):
        # type: (FileSystemEvent) -> None
        if not self._should_check_file(event.src_path):
            return
        self.last_deleted = event.src_path
        self.events.put(event)
        self._notify_event_handler()

    def on_created(self, event):
        # type: (FileSystemEvent) -> None
        if not self._should_check_file(event.src_path):
            return
        self.events.put(event)
        self._notify_event_handler()
        if event.src_path == self.last_deleted:
            self.on_modified(FileModifiedEvent(event.src_path))

    def on_modified(self, event):
        # type: (FileSystemEvent) -> None
        if not self._should_check_file(event.src_path):
            return
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

