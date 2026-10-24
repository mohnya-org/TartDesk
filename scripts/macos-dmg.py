#!/usr/bin/env python3
"""Create a signed, notarized first-install DMG from an already notarized app."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import fcntl

REQUIRED = ('APPLE_CERT_BASE64', 'APPLE_CERT_PASSWORD', 'APPLE_TEAM_ID',
            'APPLE_API_KEY_ID', 'APPLE_API_ISSUER_ID', 'APPLE_API_PRIVATE_KEY')


class DistributionError(Exception):
    pass


def run(args, stage, **kwargs):
    # security and notarytool diagnostics can contain credential arguments.
    try:
        result = subprocess.run([str(a) for a in args], capture_output=True, **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        raise DistributionError(f'{stage} failed') from None
    if result.returncode:
        raise DistributionError(f'{stage} failed')
    return result


def preflight(env=os.environ):
    missing = [name for name in REQUIRED if not env.get(name, '').strip()]
    if missing:
        raise DistributionError('Missing secrets: ' + ', '.join(missing))
    if not re.fullmatch(r'[A-Z0-9]{10}', env['APPLE_TEAM_ID']):
        raise DistributionError('Invalid APPLE_TEAM_ID')
    try:
        if not base64.b64decode(''.join(env['APPLE_CERT_BASE64'].split()), validate=True):
            raise ValueError()
    except ValueError:
        raise DistributionError('Invalid APPLE_CERT_BASE64') from None
    if '-----BEGIN PRIVATE KEY-----' not in env['APPLE_API_PRIVATE_KEY']:
        raise DistributionError('Invalid APPLE_API_PRIVATE_KEY')


def select_identity(output, team):
    identities = re.findall(r'\b([A-Fa-f0-9]{40}) "Developer ID Application: [^"\n]+ \('
                            + re.escape(team) + r'\)"', output)
    if len(set(identities)) != 1:
        raise DistributionError('Expected one valid Developer ID Application identity matching APPLE_TEAM_ID')
    return identities[0]


def register_keychain(keychain):
    # Preserve other jobs' entries and never change the default keychain.
    fd = os.open(Path(tempfile.gettempdir()) / 'mohnya-dmg-keychain.lock',
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = shlex.split(run(['security', 'list-keychains', '-d', 'user'], 'Keychain list lookup').stdout.decode())
        if str(keychain) not in current:
            run(['security', 'list-keychains', '-d', 'user', '-s', *current, keychain], 'Keychain registration')


def cleanup(directory):
    directory = Path(directory)
    if not directory.name.startswith('macos-dmg-'):
        raise DistributionError('Refusing unrelated cleanup path')
    if not directory.exists():
        return
    mount = directory / 'mount'
    if mount.is_mount():
        run(['hdiutil', 'detach', mount], 'DMG detach', timeout=120)
    keychain = directory / 'signing.keychain-db'
    failed = False
    if keychain.exists():
        failed = subprocess.run(['security', 'delete-keychain', str(keychain)], capture_output=True).returncode != 0
    for path in directory.iterdir():
        if failed and path.name.startswith('signing.keychain'):
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    if failed:
        raise DistributionError('Keychain cleanup failed; workflow cleanup must retry')
    directory.rmdir()


def verify_app(app, team):
    requirement = ('anchor apple generic and certificate leaf[subject.OU] = "' + team
                   + '" and certificate leaf[field.1.2.840.113635.100.6.1.13] exists')
    run(['codesign', '--verify', '--deep', '--strict', '-R', requirement, app], 'App signature and team verification')
    run(['xcrun', 'stapler', 'validate', app], 'App ticket verification', timeout=120)
    run(['spctl', '--assess', '--type', 'execute', app], 'App Gatekeeper assessment', timeout=120)


def verify_layout(mount, app_name, expected_info):
    link = mount / 'Applications'
    if not link.is_symlink() or os.readlink(link) != '/Applications':
        raise DistributionError('DMG Applications link is invalid')
    info = plistlib.loads((mount / app_name / 'Contents/Info.plist').read_bytes())
    for key in ('CFBundleIdentifier', 'CFBundleVersion', 'CFBundleShortVersionString'):
        if not info.get(key) or info.get(key) != expected_info.get(key):
            raise DistributionError('DMG contains an unexpected app/version')


def create(app, dmg):
    preflight()
    app, dmg = Path(app).resolve(), Path(dmg).resolve()
    if app.suffix != '.app' or not app.is_dir() or dmg.suffix != '.dmg':
        raise DistributionError('Expected app bundle and DMG output path')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', dmg.name):
        raise DistributionError('Unsafe DMG asset name')
    team = os.environ['APPLE_TEAM_ID']
    verify_app(app, team)
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    directory = Path(tempfile.mkdtemp(prefix='macos-dmg-', dir=os.environ.get('RUNNER_TEMP')))
    directory.chmod(0o700)
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a') as stream:
            stream.write(f'DMG_SIGNING_TEMP_DIR={directory}\n')
    try:
        keychain = directory / 'signing.keychain-db'
        cert, key = directory / 'certificate.p12', directory / 'AuthKey.p8'
        cert.write_bytes(base64.b64decode(''.join(os.environ['APPLE_CERT_BASE64'].split()), validate=True))
        key.write_text(os.environ['APPLE_API_PRIVATE_KEY'])
        cert.chmod(0o600)
        key.chmod(0o600)
        password = secrets.token_urlsafe(32)
        run(['security', 'create-keychain', '-p', password, keychain], 'Keychain creation')
        run(['security', 'set-keychain-settings', '-lut', '21600', keychain], 'Keychain settings')
        run(['security', 'unlock-keychain', '-p', password, keychain], 'Keychain unlock')
        run(['security', 'import', cert, '-k', keychain, '-P', os.environ['APPLE_CERT_PASSWORD'],
             '-T', '/usr/bin/codesign', '-T', '/usr/bin/security'], 'Certificate import')
        run(['security', 'set-key-partition-list', '-S', 'apple-tool:,apple:', '-s', '-k', password, keychain], 'Key access setup')
        register_keychain(keychain)
        identity = select_identity(run(['security', 'find-identity', '-v', '-p', 'codesigning', keychain], 'Identity lookup').stdout.decode(), team)
        cert.unlink()
        staging = directory / 'image'
        staging.mkdir()
        run(['ditto', app, staging / app.name], 'Copy notarized app')
        (staging / 'Applications').symlink_to('/Applications')
        dmg.parent.mkdir(parents=True, exist_ok=True)
        run(['hdiutil', 'create', '-ov', '-format', 'UDZO', '-fs', 'HFS+', '-volname', app.stem,
             '-srcfolder', staging, dmg], 'DMG creation', timeout=300)
        run(['codesign', '--force', '--sign', identity, '--keychain', keychain, '--timestamp', dmg], 'DMG signing', timeout=180)
        result = run(['xcrun', 'notarytool', 'submit', dmg, '--key', key,
                      '--key-id', os.environ['APPLE_API_KEY_ID'], '--issuer', os.environ['APPLE_API_ISSUER_ID'],
                      '--wait', '--timeout', '20m', '--output-format', 'json'], 'DMG notarization', timeout=1260)
        if json.loads(result.stdout).get('status') != 'Accepted':
            raise DistributionError('DMG notarization was not Accepted')
        print('DMG notarization Accepted', flush=True)
        run(['xcrun', 'stapler', 'staple', dmg], 'DMG stapling', timeout=120)
        run(['xcrun', 'stapler', 'validate', dmg], 'DMG ticket verification', timeout=120)
        run(['codesign', '--verify', '--strict', dmg], 'DMG signature verification')
        run(['spctl', '--assess', '--type', 'open', '--context', 'context:primary-signature', dmg], 'DMG Gatekeeper assessment', timeout=120)
        run(['hdiutil', 'verify', dmg], 'DMG integrity verification', timeout=120)
        mount = directory / 'mount'
        mount.mkdir()
        run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, dmg], 'DMG mounting', timeout=120)
        try:
            verify_layout(mount, app.name, info)
            verify_app(mount / app.name, team)
        finally:
            run(['hdiutil', 'detach', mount], 'DMG detach', timeout=120)
        digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
        dmg.with_suffix('.dmg.sha256').write_text(f'{digest}  {dmg.name}\n')
        print('DMG verified: signature, notarization, Gatekeeper, app version and Applications link', flush=True)
    finally:
        cleanup(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create', 'preflight', 'cleanup', 'register-keychain'])
    parser.add_argument('paths', nargs='*')
    args = parser.parse_args()
    if args.command == 'create' and len(args.paths) == 2:
        create(*args.paths)
    elif args.command == 'register-keychain' and len(args.paths) == 1:
        register_keychain(args.paths[0])
    elif args.command == 'preflight' and not args.paths:
        preflight()
    elif args.command == 'cleanup' and len(args.paths) == 1:
        cleanup(args.paths[0])
    else:
        parser.error('Incorrect number of paths')


if __name__ == '__main__':
    def interrupted(*_args):
        raise DistributionError('DMG creation interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        main()
    except (DistributionError, ValueError, OSError):
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, DistributionError) else 'DMG input or file operation failed', file=sys.stderr)
        sys.exit(1)
