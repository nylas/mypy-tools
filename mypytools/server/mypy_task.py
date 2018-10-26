# coding=utf-8
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import hashlib

import os
import shlex
import tempfile
import traceback
from collections import defaultdict

from subprocess import Popen, PIPE

from typing import Optional, Tuple, List, Dict

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
    def __init__(self, filename, include_error_context=True):
        # type: (str, bool) -> None
        self.filename = filename
        self._proc = None   # type: Optional[Popen]
        self.include_error_context = include_error_context

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
        # type: () -> Tuple[int, str, str, str]
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

            if exit_code == 0:
                return 0, '', '', before_file_hash

            context = ''
            if self.include_error_context:
                context = self._find_context(out)

            return exit_code, out, context, before_file_hash
        except Exception:
            traceback.print_exc()
            return -1, '', '', ''
        finally:
            self._proc = None

    def _find_context(self, errors):
        # type: (str) -> str
        error_list = errors.split('\n')
        errors_by_path = defaultdict(list)  # type: Dict[str, List[Tuple[int, str]]]
        for error in error_list:
            error_parts = error.split(':')
            if len(error_parts) != 4:
                continue
            path, line, _, message = error_parts
            errors_by_path[path].append((int(line), message))

        results = []
        for path in errors_by_path:
            results.extend(self._get_context_for_path(path, errors_by_path[path]))
        return '\n'.join(results)

    def _get_context_for_path(self, path, parsed_errors):
        # type: (str, List[Tuple[int, str]]) -> List[str]
        result = []
        template = """
  \033[91m\033[1mError\033[0m: {}
    \033[93m\033[1m{}\033[0m
        {}
  >>>   {}
        {}
"""
        target_context_lines_before = 2
        target_context_lines_after = 2
        # We seed the context lines with an empty string to get the
        # proper final padding before and after.
        context_lines_before = ['']
        context_lines_after = ['']

        with open(path, 'r') as f:
            lines = f.readlines()
            # Insert a blank line so that 1-indexed line numbers from errors match.
            lines.insert(0, '')

            for line, message in parsed_errors:
                begin_line = max(0, line - target_context_lines_before)
                end_line = min(len(lines), line + target_context_lines_after + 1)

                for num, l in enumerate(lines[begin_line:line]):
                    context_lines_before.append('{} {}'.format(begin_line + num, l.rstrip('\n')))

                context_line = '{} {}'.format(line, lines[line].rstrip('\n'))

                for num, l in enumerate(lines[line + 1:end_line]):
                    context_lines_after.append('{} {}'.format(line + num + 1, l.rstrip('\n')))

                error_lines = [
                    '\n'.join(context_lines_before),
                    context_line,
                    '\n'.join(context_lines_after),
                ]

                # Insert the location.
                error_lines.insert(0, '{}:{}'.format(path, line))

                # Insert the error message.
                error_lines.insert(1, message)

                result.append(template.format(*error_lines))
        return result

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

