#!/usr/bin/env python3
"""Temporarily register a signing keychain without replacing other jobs' entries."""
from keychain_lock import keychain_lock
import os
import shlex
import subprocess
import sys


def update_search_list(keychain, add):
    with keychain_lock():
        result = subprocess.run(['security', 'list-keychains', '-d', 'user'],
                                check=True, capture_output=True, text=True)
        current = shlex.split(result.stdout)
        target = os.path.realpath(keychain)
        matches = lambda path: os.path.realpath(path) == target
        if add:
            updated = current if any(map(matches, current)) else current + [keychain]
        else:
            # Read current state rather than restoring a stale snapshot: another
            # job may have legitimately added/removed its own keychain meanwhile.
            updated = [path for path in current if not matches(path)]
        if updated != current:
            subprocess.run(['security', 'list-keychains', '-d', 'user', '-s', *updated],
                           check=True, capture_output=True)


if __name__ == '__main__':
    try:
        action, keychain = sys.argv[1:3]
        if action == 'attach':
            update_search_list(keychain, True)
        elif action == 'detach':
            update_search_list(keychain, False)
        else:
            sys.exit('Unknown signing keychain action')
    except (OSError, subprocess.CalledProcessError):
        sys.exit('Could not update signing keychain search list')
