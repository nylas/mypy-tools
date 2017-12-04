#!/usr/bin/env python
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division
from typing import Dict, Optional, List, Set  # noqa

from mypytools import source_utils
from mypytools.config import config

import ast
import click
import os


class SourceObj(object):
    def __init__(self, name):
        # type: (str) -> None
        self.name = name
        self.num_annotated_funcs = 0
        self.num_scanned_funcs = 0
        self.parent = None  # type: Optional[SourceObj]
        self.children = {}  # type: Dict[str, SourceObj]

    def coverage(self):
        # type: () -> float
        if self.num_scanned_funcs == 0:
            return 0.0
        return float(self.num_annotated_funcs) / float(self.num_scanned_funcs)

    def add_child(self, child):
        # type: (SourceObj) -> None
        self.children[child.name] = child
        child.parent = self
        self.refresh()

    def refresh(self):
        # type: () -> None
        if len(self.children) > 0:
            self.num_annotated_funcs = 0
            self.num_scanned_funcs = 0

            for child_name in self.children:
                child = self.children[child_name]
                self.num_annotated_funcs += child.num_annotated_funcs
                self.num_scanned_funcs += child.num_scanned_funcs

        if self.parent:
            self.parent.refresh()

    def sorted_output(self, indent, output_lines, max_depth=None):
        # type: (int, List[str], Optional[int]) -> None
        if max_depth is not None and max_depth == 0:
            return
        spaces = ' ' * (indent * 4)
        percent = 100.0 * self.coverage()
        output_lines.append("{spaces}{0}: {1}/{2} ({3:.2f}%%)".format(
            self.name,
            self.num_annotated_funcs,
            self.num_scanned_funcs,
            percent,
            spaces=spaces))
        sorted_children = sorted(list(self.children.items()), key=lambda c: c[1].coverage(), reverse=True)
        max_depth = None if max_depth is None else max_depth - 1
        for child_name, child in sorted_children:
            child.sorted_output(indent + 1, output_lines, max_depth)

    def sorted_print(self, indent, max_depth=None):
        # type: (int, Optional[int]) -> None
        output_lines = []   # type: List[str]
        self.sorted_output(indent, output_lines, max_depth)
        print('\n'.join(output_lines))


def add_new_leaf_node(root, path, num_annotated_funcs, num_scanned_funcs):
    # type: (SourceObj, str, int, int) -> None
    path_parts = path.split('/')
    curr = root
    for part in path_parts:
        next_dir = curr.children.get(part)
        if next_dir is None:
            next_dir = SourceObj(part)
            curr.add_child(next_dir)
        curr = next_dir
    curr.num_annotated_funcs = num_annotated_funcs
    curr.num_scanned_funcs = num_scanned_funcs
    curr.refresh()


def process_source(root, path, source):
    # type: (SourceObj, str, str) -> None
    lines, tree = source_utils.parse_source(source)
    num_scanned_funcs = 0
    num_annotated_funcs = 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        num_scanned_funcs += 1
        if source_utils.is_func_def_annotated(node, lines):
            num_annotated_funcs += 1

    add_new_leaf_node(root, path, num_annotated_funcs, num_scanned_funcs)


def process_file(root, filename):
    # type: (SourceObj, str) -> None
    with open(filename, 'r') as f:
        source = f.read()
    process_source(root, filename, source)


def is_python_file(path):
    # type: (str) -> bool
    if path.endswith('.py'):
        return True
    try:
        with open(path, 'rb') as f:
            first_line = f.readline().rstrip(b'\n')
            if first_line.startswith(b'#!') and first_line.endswith(b'python'):
                return True
    except IOError:
        pass
    return False


@click.command()
@click.option('--max-depth', default=None, type=int)
def main(max_depth):
    # type: (Optional[int]) -> None
    root = SourceObj('root')

    src_dirs = [os.path.join(config['root_dir'], d['path']) for d in config['src_dirs']]

    paths = set()   # type: Set[str]
    for src_dir in src_dirs:
        for dirpath, dirnames, filenames in os.walk(src_dir):
            for filename in filenames:
                path = os.path.join(dirpath, filename)
                if not is_python_file(path):
                    continue
                paths.add(path)

    for path in paths:
        process_file(root, path)

    root.sorted_print(indent=0, max_depth=max_depth)


if __name__ == "__main__":
    main()
