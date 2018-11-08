from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import ast
import re

from typing import List, Tuple, Optional

DECORATOR_PATTERN = re.compile(r'^\s*@')
TYPE_PATTERN = re.compile(r'^\s+#\s+type:\s+')


def find_final_line_including_parens(lines, line_num):
    # type: (List[str], int) -> int
    # It's very challenging to find the *end* of a decorator.
    # The python ast gives us the start line, but a decorator
    # is essentially a function call that can span multiple lines,
    # contain any literal arguments (e.g. strings), etc.
    # This function attempts to account for all of those cases,
    # but using a real lexer would probably be better.

    # Check if the statement spans multiple lines using parens.
    line = lines[line_num]
    lparen_loc = line.find('(')

    # If there's no lparen then we're done.
    if lparen_loc == -1:
        return line_num

    # There's an lparen so find the matching rparen.
    loc = lparen_loc + 1
    lparen_depth = 1
    escape_char = False
    string_char = None  # type: Optional[str]
    while lparen_depth > 0:
        if loc >= len(line):
            line_num += 1
            line = lines[line_num]
            loc = 0
            continue

        if string_char is not None:
            # This is either the start of an escaped character
            # (e.g. "\"") or it could be the second character in
            # an escaped sequence ("\\"). In either case, we want
            # to flip the value of escape_char and go to the next
            # character.
            if line[loc] == '\\':
                escape_char = not escape_char

            # This is the second part of an escaped character sequence
            # so clear escape_char and keep going.
            elif escape_char:
                escape_char = False

            # This isn't an escaped character so check for the end of the string.
            # The substring-ing part of this check is to handle the end of block strings.
            elif line[loc:loc + len(string_char)] == string_char:
                string_char = None

            # While inside a string skip the contents.
            loc += 1
            continue

        # Check for the beginning of a string.
        if line[loc] in '\'"':
            # Handle block strings.
            if line[loc:loc + 3] == line[loc] * 3:
                string_char = line[loc] * 3
            else:
                string_char = line[loc]

        # Check for the beginning of a comment, advance to end of line.
        elif line[loc] == '#':
            loc = len(line)
            continue

        # We're not a string and we're not an escaped character,
        # so check for parens.
        elif line[loc] == '(':
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
    """ Produce True if either Python3 or Python2 style type annotations found
    for the given function
    """
    if getattr(func, 'returns', None):
        return True

    for arg in func.args.args:
        if getattr(arg, 'annotation', None):
            return True

    first_line_num = find_first_line_of_func(lines, func.lineno)
    first_line = lines[first_line_num]
    if is_line_annotated(first_line):
        return True

    end_line_of_def = lines[first_line_num - 1]
    function_definition, rest = end_line_of_def.split(':', 1)
    if is_line_annotated(rest):
        return True

    return False


def parse_source(source):
    # type: (str) -> Tuple[List[str], ast.AST]
    lines = source.split('\n')
    tree = ast.parse(source)
    lines.insert(0, '')
    return lines, tree


