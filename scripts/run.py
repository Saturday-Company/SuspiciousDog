"""Runs sdog from a copy of the code (the Claude Code plugin), safely: `python3 -I scripts/run.py <command>`.

`python3 -m suspiciousdog` would put the current folder first on the import path, so a file in the project you
opened (say, a `json.py`) could run in its place. `-I` leaves the current folder and the environment out; this file
adds only the package's own folder.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suspiciousdog.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
