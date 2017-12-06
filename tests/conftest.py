import sys

collect_ignore = []
if sys.version_info[0] > 2:
    collect_ignore.append("py2")
else:
    collect_ignore.append("py3")