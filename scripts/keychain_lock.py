"""Coordinate keychain search-list mutations across apps and runner directories."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys


@contextmanager
def keychain_lock():
    # Per-user, host-wide path: RUNNER_TEMP/TMPDIR can differ between runners.
    path = Path('/private/tmp') / f'mohnya-signing-keychains-{os.getuid()}.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        if os.fstat(lock.fileno()).st_uid != os.getuid():
            raise OSError('Unexpected keychain lock owner')
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ('create-keychain', 'delete-keychain'):
        raise SystemExit('Expected create-keychain or delete-keychain arguments')
    with keychain_lock():
        result = subprocess.run(['security', *sys.argv[1:]], capture_output=True)
    if result.returncode:
        raise SystemExit('Keychain mutation failed (raw output suppressed)')


if __name__ == '__main__':
    main()
