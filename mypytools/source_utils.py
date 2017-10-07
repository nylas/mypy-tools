from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import ast
import re

DECORATOR_PATTERN = re.compile(r'^\s*@')
TYPE_PATTERN = re.compile(r'^\s+#\s+type:\s+')


def find_final_line_including_parens(lines, line_num):
    # type: (List[str], int) -> int
    # Check if the statement spans multiple lines using parens.
    line = lines[line_num]
    lparen_loc = line.find('(')

    # If there's no lparen then we're done.
    if lparen_loc == -1:
        return line_num

    # There's an lparen so find the matching rparen.
    loc = lparen_loc + 1
    lparen_depth = 1
    while lparen_depth > 0:
        if loc >= len(line):
            line_num += 1
            line = lines[line_num]
            loc = 0
            continue
        if line[loc] == '(':
            lparen_depth += 1
        elif line[loc] == ')':
            lparen_depth -= 1
        loc += 1
    return line_num


def find_first_line_of_func(lines, line_num):
    # type: (List[str], int) -> int
    while True:
        result = DECORATOR_PATTERN.search(lines[line_num])
        if result is None:
            break
        end_line_of_decorator = find_final_line_including_parens(lines, line_num)
        line_num = end_line_of_decorator + 1

    # We're now at the function def line
    end_line_of_def = find_final_line_including_parens(lines, line_num)
    return end_line_of_def + 1


def is_line_annotated(line):
    # type: (str) -> bool
    result = TYPE_PATTERN.search(line)
    return result is not None


def is_func_def_annotated(func, lines):
    # type: (ast.FunctionDef, List[str]) -> bool
    first_line_num = find_first_line_of_func(lines, func.lineno)
    first_line = lines[first_line_num]
    return is_line_annotated(first_line)


def parse_source(source):
    # type: (str) -> Tuple[List[str], ast.AST]
    lines = source.split('\n')
    tree = ast.parse(source)
    lines.insert(0, '')
    return lines, tree


