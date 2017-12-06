#!/usr/bin/env python
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division
from typing import Dict, List, Optional, Set    # noqa

import ast
import click
import os
import re
import subprocess

from mypytools import source_utils

UNIFIED_DIFF_REGEX = re.compile(r'^(\d+)(,(\d+))?$')


def visit_node(root, line_to_func_map):
    # type: (ast.AST, Dict[int, Optional[ast.FunctionDef]]) -> None
    active_function = None  # type: Optional[ast.FunctionDef]
    to_visit = [(root, active_function)]
    while len(to_visit) > 0:
        curr_node, active_function = to_visit.pop()
        for child_node in ast.iter_child_nodes(curr_node):
            if not getattr(child_node, 'lineno', None):
                continue
            if isinstance(child_node, ast.FunctionDef):
                line_to_func_map[child_node.lineno] = child_node
                to_visit.append((child_node, child_node))
            else:
                line_to_func_map[child_node.lineno] = active_function   # type: ignore
                to_visit.append((child_node, active_function))


def fill_line_to_func_gaps(line_to_func_map, num_lines):
    # type: (Dict[int, Optional[ast.FunctionDef]], int) -> None
    active_function = None
    curr_line = 1
    for line_num in sorted(line_to_func_map):
        for missing_line_num in range(curr_line, line_num):
            line_to_func_map[missing_line_num] = active_function
        active_function = line_to_func_map[line_num]
        curr_line = line_num

    if len(line_to_func_map) == 0:
        curr_line = 0
    for line_num in range(curr_line + 1, num_lines + 1):
        line_to_func_map[line_num] = active_function


def get_added_lines(filename, rev):
    # type: (str, str) -> Set[int]
    added_lines = subprocess.check_output("git diff --unified=0 {} {} | grep @@ | cut -d'+' -f2 | cut -f1 -d' '".format(rev, filename), universal_newlines=True, shell=True).split('\n')
    results = set()
    for line in added_lines:
        result = UNIFIED_DIFF_REGEX.match(line)
        if result is None:
            continue
        groups = result.groups()
        start = int(groups[0])
        if groups[2] is None:
            results.add(start)
        else:
            num_lines = int(groups[2])
            for i in range(num_lines):
                results.add(start + i)
    return results


def get_modified_files(rev):
    # type: (str) -> List[str]
    relative_paths = subprocess.check_output("git diff --name-only {}".format(rev), shell=True, universal_newlines=True).split('\n')[0:-1]
    repo_root = subprocess.check_output("git rev-parse --show-toplevel", shell=True, universal_newlines=True).split('\n')[0]

    python_paths = []
    for path in relative_paths:
        abs_path = os.path.join(repo_root, path)
        if path.endswith(".py"):
            python_paths.append(abs_path)
            continue

        try:
            with open(abs_path, 'r') as f:
                first_line = f.readline().rstrip('\n')
                if first_line.startswith('#!') and first_line.endswith('python'):
                    python_paths.append(abs_path)
                    continue
        except IOError:
            continue

    return python_paths


def process_source(lines, added_lines, line_to_func_map):
    # type: (List[str], Set[int], Dict[int, Optional[ast.FunctionDef]]) -> List[int]
    results = []    # type: List[int]
    printed_funcs = set()   # type: Set[ast.FunctionDef]
    for line_num in sorted(added_lines):
        func_def = line_to_func_map[line_num]
        if func_def is None or func_def in printed_funcs:
            continue

        if source_utils.is_func_def_annotated(func_def, lines):
            continue

        first_line_num = source_utils.find_first_line_of_func(lines, func_def.lineno)

        results.append(first_line_num)
        printed_funcs.add(func_def)
    return results


def process_file(filename, rev):
    # type: (str, str) -> None
    line_to_func_map = {}   # type: Dict[int, Optional[ast.FunctionDef]]

    try:
        with open(filename, 'r') as f:
            source = f.read()
    except IOError:
        return

    lines, tree = source_utils.parse_source(source)
    added_lines = get_added_lines(filename, rev)
    visit_node(tree, line_to_func_map)
    fill_line_to_func_gaps(line_to_func_map, len(lines))
    error_lines = process_source(lines, added_lines, line_to_func_map)
    for line_num in error_lines:
        print('{}:{} Please add a mypy annotation!'.format(filename, line_num))


@click.command()
@click.argument('rev')
def main(rev):
    # type: (str) -> None
    modified_files = get_modified_files(rev)
    for filename in modified_files:
        if filename == '':
            continue
        process_file(filename, rev)


if __name__ == "__main__":
    main()
