#!/usr/bin/env python3
"""Exercise the real host-wide lock with independent runner-like processes."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from keychain_lock import keychain_lock


class SharedLockTests(unittest.TestCase):
    def test_independent_processes_do_not_lose_updates(self):
        script = '''
import sys, time
from pathlib import Path
from keychain_lock import keychain_lock
state = Path(sys.argv[1])
for _ in range(5):
    with keychain_lock():
        count = int(state.read_text())
        time.sleep(0.01)
        state.write_text(str(count + 1))
'''
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'search-list-counter'
            state.write_text('0')
            processes = [subprocess.Popen([sys.executable, '-B', '-c', script, str(state)],
                         cwd=Path(__file__).parent) for _ in range(4)]
            for process in processes:
                self.assertEqual(process.wait(timeout=15), 0)
            self.assertEqual(state.read_text(), '20')

    def test_exception_releases_lock(self):
        with self.assertRaisesRegex(RuntimeError, 'expected'):
            with keychain_lock():
                raise RuntimeError('expected')
        subprocess.run([sys.executable, '-B', '-c',
                        'from keychain_lock import keychain_lock\nwith keychain_lock(): pass'],
                       cwd=Path(__file__).parent, check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
