#!/usr/bin/env python
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import ast  # noqa

from typing import Optional, Dict, Set, List  # noqa

from bin.check_mypy_annotations import fill_line_to_func_gaps, process_source, visit_node
from mypytools import source_utils


def get_error_lines(source, added_lines):
    # type: (str, Set[int]) -> List[int]
    line_to_func_map = {}  # type: Dict[int, Optional[ast.FunctionDef]]
    lines, tree = source_utils.parse_source(source)
    visit_node(tree, line_to_func_map)
    fill_line_to_func_gaps(line_to_func_map, len(lines))
    return process_source(lines, added_lines, line_to_func_map)


def test_no_annotation():
    # type: () -> None

    source = """
def update_app(app_client_id):
    return None
    """

    error_lines = get_error_lines(source, {3})
    assert error_lines == [3]


def test_decorator_offset():
    # type: () -> None
    source = """@blueprint.route('/<app_client_id>/update', methods=['PUT'])
def update_app(app_client_id):
    # type: (str) -> Response
    return None
"""
    error_lines = get_error_lines(source, {4})
    assert len(error_lines) == 0


def test_normal_offset():
    # type: () -> None
    source = """def test_normal_offset():
    # type: () -> None
    return None
"""
    error_lines = get_error_lines(source, {4})
    assert len(error_lines) == 0


def test_multiline_func_def():
    # type: () -> None
    source = """def test_normal_offset(a,
                                       b):
    # type: () -> None
    return None
"""
    error_lines = get_error_lines(source, {4})
    assert len(error_lines) == 0


def test_multiline_decorator():
    # type: () -> None
    source = """
@foo('bar',
    'baz')
def test_normal_offset():
    # type: () -> None
    return None
"""
    error_lines = get_error_lines(source, {6})
    assert len(error_lines) == 0


def test_multiline_decorator2():
    # type: () -> None
    source = """
@pytest.mark.parametrize('nspid, mspid', [
    ('][][][][][][', '\\\\\\'(*&^sdfsaf^%')
])
def test_foo(nspid, mspid):
    # type: (str, str) -> None
    with pytest.raises(InputError):
        foo_bar_baz(nspid, mspid)

"""
    error_lines = get_error_lines(source, {7})
    assert len(error_lines) == 0


def test_multiline_decorator3():
    # type: () -> None
    source = """
@click.option(
    '--process_num',
    default=0,
    help="This process's number in the process group: a unique "
    "number satisfying 0 <= process_num < total_processes.")
def sync(process_num,  # type: int
        ):
    # type: (...) -> None
    pass

"""
    error_lines = get_error_lines(source, {10})
    assert len(error_lines) == 0


def test_correct_offset():
    # type: () -> None
    source = """
@blueprint.route('/', methods=['POST'])
def create():
    if not g.features.contacts_crud:
        return err(400, "This isn't supported in the version of the API your app uses. "
                        "Please update the API version for your app in the developer dashboard. "
                        "https://dashboard.com ")
    """
    error_lines = get_error_lines(source, {6})
    assert error_lines == [4]


def test_short_form_close_parenthesis_line():
    # type: () -> None
    source = """
def foo(a, b):  # type: (int, int) -> int
    return a + b
    """
    error_lines = get_error_lines(source, {3})
    assert error_lines == []
