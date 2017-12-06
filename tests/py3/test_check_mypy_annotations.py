from tests.test_check_mypy_annotations import get_error_lines


def test_python3():
    # type: () -> None
    source = """
def foo(a: int, b) -> int:
    return a + b
    """
    error_lines = get_error_lines(source, {3})
    assert error_lines == []