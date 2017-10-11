from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import json
import os

from typing import Dict, Any

config = {}     # type: Dict[str, Any]


def load_config_file():
    # type: () -> None
    global config
    cwd = os.getcwd()
    while True:
        config_path = os.path.join(cwd, '.mypy_server')
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                config['root_dir'] = cwd
                break
        except IOError:
            new_cwd = os.path.dirname(cwd)
            if new_cwd == cwd:
                raise RuntimeError('Unable to find .mypy_server config file')
            cwd = new_cwd
            continue
        except ValueError:
            print('Error while loading the config file. Maybe a JSON syntax error?')
            raise

load_config_file()
