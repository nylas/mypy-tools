from tests.test_print_mypy_coverage import process_files


def test_python3():
    # type: () -> None
    files = [
        ("""
def foo():
    pass
    """, 'a/a.py'),
    ("""
def bar() -> None:
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