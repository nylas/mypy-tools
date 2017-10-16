# coding=utf-8
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import hashlib

import os
import shlex

from subprocess import Popen, PIPE

from typing import Optional, Tuple

from mypytools.config import config


STRICT_OPTIONAL_DIRS = [os.path.join(config['root_dir'], d['path']) for d in config['src_dirs'] if d.get('strict_optional')]


# From https://stackoverflow.com/a/377028
def which(program):
    # type: (str) -> Optional[str]
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None


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
        flags = ' '.join(config.get('global_flags', []))
        strict_optional = '--strict-optional' if self._should_use_strict_optional(self.filename) else ''
        mypy_exec = which('mypy')
        if mypy_exec is None:
            print("Couldn't find mypy executable. Is it installed and in your PATH?")
            raise RuntimeError('Mypy executable missing.')

        cmd = shlex.split("{} {} {} {}".format(mypy_exec, flags, strict_optional, self.filename))
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

