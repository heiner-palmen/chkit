"""Files on shared folders (a NAS mounted via CIFS) without surprises.

* Writing goes through a temp file next to the target and a rename, so a
  reader (OBS, another PC) never sees half a file.
* Anything that touches a network folder that may hang runs as a child
  process with a timeout: a stale CIFS mount blocks every file access for
  minutes, and a child can be killed.
* JSON that is caught in the middle of a write reads as "nothing yet".
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Callable, Optional, Union

# prints the file, or nothing if there is none; fails only if the folder cannot be reached
_FETCH = 'cd "$1" && { if [ -f "$2" ]; then cat -- "$2"; fi; exit 0; }'


def write_atomic(path: str, data: Union[str, bytes], mode: int = 0o644) -> None:
    """Temp file in the same folder, then rename over `path`."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_json_atomic(path: str, obj, indent: Optional[int] = 2) -> None:
    write_atomic(path, json.dumps(obj, ensure_ascii=False, indent=indent) + "\n")


def read_json(path: str):
    """The JSON in `path`, None if missing, unreadable or half written."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    try:
        return json.loads(text) if text.strip() else None
    except ValueError:
        return None


def copy_with_timeout(src: str, dst: str, timeout_s: float = 5, check: Optional[Callable[[str], None]] = None,
                      run=subprocess.run) -> Optional[str]:
    """Copy `src` (e.g. on the NAS) over `dst` with `cp` in a child process.
    `check(path)` may raise ValueError/OSError to refuse a copy; `dst` is only
    replaced by a copy that passed it. Returns None on success, else why not."""
    tmp = dst + ".new"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        run(["cp", "--", src, tmp], check=True, timeout=timeout_s,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check:
            check(tmp)
        os.replace(tmp, dst)
        return None
    except subprocess.TimeoutExpired:
        reason = f"no answer within {timeout_s:g} s"
    except subprocess.CalledProcessError:
        reason = "not readable (not mounted?)"
    except (OSError, ValueError) as e:
        reason = f"unusable: {e}"
    try:
        os.remove(tmp)
    except OSError:
        pass
    return reason


def fetch_text(folder: str, name: str, timeout_s: float = 3, run=subprocess.run) -> Optional[str]:
    """The text of folder/name read by a child process: "" if the file does
    not exist, None if the folder does not answer (missing mount, hanging NAS)."""
    try:
        done = run(["sh", "-c", _FETCH, "sh", folder, name], check=True, timeout=timeout_s,
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError):
        return None
    return done.stdout.decode("utf-8", errors="replace")
