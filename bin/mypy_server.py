#!/usr/bin/env python
import click
from mypytools.server import mypy_server


@click.command()
@click.option('--compact', is_flag=True, default=False, help="Print mypy errors without surrounding code context.")
def main(compact):
    # type: (bool) -> None
    mypy_server.run_server(compact=compact)

if __name__ == "__main__":
    main()
