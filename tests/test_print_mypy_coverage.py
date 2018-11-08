from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from typing import List, Tuple  # noqa

from bin.print_mypy_coverage import process_source, SourceObj


def process_files(files):
    # type: (List[Tuple[str, str]]) -> List[str]
    root = SourceObj('root')
    for source, path in files:
        process_source(root, path, source)
    output_lines = []   # type: List[str]
    root.sorted_output(0, output_lines, max_depth=None)
    return output_lines


def test_single_file():
    # type: () -> None
    files = [("""
def foo():
    pass
    """, 'a.py')]
    output_lines = process_files(files)
    assert output_lines == [
        'root: 0/1 (0.00%)',
        '    a.py: 0/1 (0.00%)',
    ]

def test_double_file():
    # type: () -> None
    files = [
        ("""
def foo():
    pass
    """, 'a/a.py'),
        ("""
def bar():
    # type: () -> None
    pass
    """, 'a/b.py'),
    ]
    output_lines = process_files(files)
    assert output_lines == [
        'root: 1/2 (50.00%)',
        '    a: 1/2 (50.00%)',
        '        b.py: 1/1 (100.00%)',
        '        a.py: 0/1 (0.00%)'
    ]
