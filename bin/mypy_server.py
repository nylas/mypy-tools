#!/usr/bin/env python
import multiprocessing

import click
from mypytools.server import mypy_server


@click.command()
@click.option('--compact', is_flag=True, default=False, help="Print mypy errors without surrounding code context.")
@click.option('--num-workers', default=multiprocessing.cpu_count())
def main(compact, num_workers):
    # type: (bool, int) -> None
    mypy_server.run_server(compact=compact, num_workers=num_workers)

if __name__ == "__main__":
    main()
