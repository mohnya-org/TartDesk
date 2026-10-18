#!/usr/bin/env python3
import base64
import importlib.util
from pathlib import Path
import tempfile
import os
import shutil
import subprocess
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('security_checks', Path(__file__).with_name('release-security.py'))
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class SecurityTests(unittest.TestCase):
    def env(self):
        env = dict.fromkeys(checks.REQUIRED, 'secret-value-not-for-logs')
        env.update(APPLE_TEAM_ID='ABCDEFGHIJ',
                   APPLE_CERT_BASE64=base64.b64encode(b'certificate').decode(),
                   SPARKLE_PUBLIC_ED_KEY=base64.b64encode(bytes(32)).decode())
        return env

    def test_valid_preflight(self):
        checks.preflight(self.env())

    def test_wrapped_certificate_matches_original_bytes(self):
        env = self.env()
        encoded = env['APPLE_CERT_BASE64']
        env['APPLE_CERT_BASE64'] = ' \t' + '\r\n'.join(encoded[i:i+4] for i in range(0, len(encoded), 4)) + '\n'
        checks.preflight(env)
        self.assertEqual(checks.decode_certificate(env['APPLE_CERT_BASE64']), b'certificate')

    def test_certificate_rejects_invalid_characters_and_padding(self):
        for value in ('YQ==!', 'YQ', ' \n', 'YQ==\u00a0'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, '^Invalid secret: APPLE_CERT_BASE64$'):
                    checks.decode_certificate(value)

    def test_all_missing_names_reported_without_values(self):
        env = self.env()
        env['APPLE_CERT_PASSWORD'] = ''
        env['APPLE_API_KEY_ID'] = '  '
        with self.assertRaises(ValueError) as result:
            checks.preflight(env)
        self.assertEqual(str(result.exception), 'Missing secrets: APPLE_API_KEY_ID, APPLE_CERT_PASSWORD')

    def test_malformed_secrets_do_not_leak(self):
        for name in ('APPLE_CERT_BASE64', 'SPARKLE_PUBLIC_ED_KEY', 'APPLE_TEAM_ID'):
            with self.subTest(name=name):
                env = self.env()
                env[name] = 'sensitive-invalid-value!'
                with self.assertRaisesRegex(ValueError, '^Invalid secret: ' + name + '$'):
                    checks.preflight(env)

    def test_archive_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'release.zip'
            for entry in ('TartDesk.app/Contents/Frameworks/Sparkle.framework/._Resources',
                          '__MACOSX/TartDesk.app/Contents/._Info.plist'):
                with zipfile.ZipFile(archive, 'w') as output:
                    output.writestr(entry, b'metadata')
                with self.assertRaisesRegex(ValueError, 'AppleDouble'):
                    checks.check_archive(archive)

    def test_clean_archive_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'release.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('TartDesk.app/Contents/Info.plist', b'plist')
            checks.check_archive(archive)


class PipelineTests(unittest.TestCase):
    def run_pipeline(self, failure):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(Path(__file__).parent, root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
            (root / 'dist/TartDesk.app').mkdir(parents=True)
            (root / 'bin').mkdir()
            mock = root / 'bin/mock'
            mock.write_text(r"""#!/usr/bin/env python3
import json, os, pathlib, sys, zipfile
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
failure = os.environ['FAILURE']
with open('calls', 'a') as log:
    log.write(name + ' ' + (args[0] if args else '') + '\n')
if name == 'security' and args[0] == 'list-keychains':
    state = pathlib.Path('search-list.json')
    entries = json.loads(state.read_text()) if state.exists() else ['/fixture/login.keychain-db']
    if '-s' in args:
        entries = args[args.index('-s') + 1:]
        state.write_text(json.dumps(entries))
    else:
        for entry in entries:
            print(json.dumps(entry))
if name == 'codesign' and args[0] == '--force':
    entries = json.loads(pathlib.Path('search-list.json').read_text())
    assert args[args.index('--keychain') + 1] in entries
    # Model a different job registering a keychain while this job signs.
    if '/fixture/other-job.keychain-db' not in entries:
        entries.append('/fixture/other-job.keychain-db')
        pathlib.Path('search-list.json').write_text(json.dumps(entries))
if name == 'security' and args[0] == 'find-identity':
    team = 'WRONGTEAM1' if failure == 'team' else 'ABCDEFGHIJ'
    print('1) ' + 'A'*40 + ' "Developer ID Application: Test (' + team + ')"')
if name == 'security' and args[0] == 'import':
    assert pathlib.Path(args[1]).read_bytes() == b'certificate'
if name == 'security' and args[0] == 'import' and failure == 'import':
    sys.exit(1)
if name == 'codesign' and args[0] == '-dv':
    print('TeamIdentifier=ABCDEFGHIJ\nAuthority=Developer ID Application: Test\nflags=0x10000(runtime)\nTimestamp=test', file=sys.stderr)
if name == 'codesign' and args[0] == '--force' and failure == 'sign':
    sys.exit(1)
if name == 'codesign' and args[0] == '--verify' and failure == 'verify':
    sys.exit(1)
if name == 'xcrun' and args[:2] == ['stapler', 'validate'] and failure == 'ticket':
    sys.exit(1)
if name == 'ditto':
    with zipfile.ZipFile(args[-1], 'w') as archive:
        archive.writestr('TartDesk.app/Contents/Info.plist', b'fixture')
if name == 'xcrun' and args[0] == 'notarytool':
    print(json.dumps({'status': 'Invalid' if failure == 'notary' else 'Accepted'}))
if name == 'xcrun' and args[:2] == ['stapler', 'staple'] and failure == 'staple':
    sys.exit(1)
if name == 'spctl' and failure == 'gatekeeper':
    sys.exit(1)
""")
            mock.chmod(0o755)
            for command in ('security', 'codesign', 'ditto', 'xcrun', 'spctl', 'xattr'):
                (root / 'bin' / command).symlink_to(mock)
            env = os.environ.copy()
            env.update(SecurityTests().env())
            encoded = env['APPLE_CERT_BASE64']
            env['APPLE_CERT_BASE64'] = ' \t' + '\r\n'.join(encoded[i:i+4] for i in range(0, len(encoded), 4)) + '\n'
            env.update(PATH=str(root / 'bin') + ':' + env['PATH'], FAILURE=failure,
                       RUNNER_TEMP=str(root), ZIP_PATH=str(root / 'release.zip'),
                       CHECKSUM_PATH=str(root / 'checksum'), GITHUB_ENV=str(root / 'env'))
            result = subprocess.run(['bash', 'scripts/notarize-release.sh'], cwd=root,
                                    env=env, text=True, capture_output=True)
            calls = (root / 'calls').read_text()
            self.assertIn('security delete-keychain', calls)
            self.assertFalse(list(root.glob('tartdesk-signing.*')))
            state = root / 'search-list.json'
            if state.exists():
                import json
                entries = json.loads(state.read_text())
                expected = ['/fixture/login.keychain-db']
                if 'codesign --force' in calls:
                    expected.append('/fixture/other-job.keychain-db')
                self.assertEqual(entries, expected)
            self.assertNotIn('security default-keychain', calls)
            self.assertNotIn('secret-value-not-for-logs', result.stdout + result.stderr)
            if failure:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse((root / 'checksum').exists())
                if failure == 'notary':
                    self.assertNotIn('xcrun stapler', calls)
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue((root / 'checksum').is_file())

    def test_success(self):
        self.run_pipeline('')

    def test_failure_blocks_checksum_and_cleans_credentials(self):
        for failure in ('import', 'team', 'sign', 'verify', 'notary', 'staple', 'ticket', 'gatekeeper'):
            with self.subTest(failure=failure):
                self.run_pipeline(failure)


if __name__ == '__main__':
    unittest.main()
