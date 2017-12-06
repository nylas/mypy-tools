# mypy-tools [![Build Status](https://travis-ci.org/nylas/mypy-tools.svg?branch=master)](https://travis-ci.org/nylas/mypy-tools)
A handful of tools to make using mypy a little easier.

## Installing
Just run `pip install mypytools`

## Typechecking server
`mypy_server.py` is a multithreaded typechecking server for MyPy. It loads a dependency graph for the Python files in a set of directories. When one of the files is modified, it typechecks that file along with all files which depend on it. You can configure it for your project by adding a `.mypy_server` file at the root of your project. See the example in this repository.

## Linter for new annotations
`check_mypy_annotations.py` is a script that can be used in combination with a linter to encourage users to add type annotations to functions they've modified. It compares the current `HEAD` to `master`, attributes all new lines back to their associated function, and prints an error if that function doesn't have type annotations.

## Annotation coverage
`print_mypy_coverage.py` is a script to print how many functions have MyPy type annotations. It consumes a list of Python files which it scans for annotations and then prints a directory hierarchy along with the associated annotation coverage.

## Custom arcanist linter
`MypyLinter.php` is a custom linter for the arcanist CLI for phabricator. It interacts directly with `mypy_server.py` and `check_mypy_annotations.py` to give `arc lint` MyPy superpowers.
