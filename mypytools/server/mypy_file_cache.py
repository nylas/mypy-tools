from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import hashlib
from typing import Dict, Tuple, Optional


class MypyFileCache(object):
    def __init__(self):
        # type: () -> None
        self._cache = {}    # type: Dict[str, Tuple[str, str]]

    def lookup(self, filename_hash, file_hash):
        # type: (str, int) -> Optional[str]
        result = self._cache.get(filename_hash)
        if result is None:
            return None
        if result[0] != file_hash:
            return None
        return result[1]

    def store(self, filename, file_hash, output):
        # type: (str, str, str) -> None
        self._cache[hashlib.md5(filename.encode('utf-8')).hexdigest()] = (file_hash, output)

