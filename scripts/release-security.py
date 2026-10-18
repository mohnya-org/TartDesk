#!/usr/bin/env python3
"""Small, independently testable release security checks. Never print secret values."""
import base64
import os
import re
import sys
import zipfile

REQUIRED = ('APPLE_API_ISSUER_ID', 'APPLE_API_KEY_ID', 'APPLE_API_PRIVATE_KEY',
            'APPLE_CERT_BASE64', 'APPLE_CERT_PASSWORD', 'APPLE_TEAM_ID',
            'SPARKLE_PRIVATE_KEY', 'SPARKLE_PUBLIC_ED_KEY')


def decode_certificate(value):
    # Base64 tools commonly wrap certificates or append a final newline.
    # Ignore ASCII whitespace only; keep rejecting all other invalid characters.
    try:
        data = base64.b64decode(re.sub(r'[ \t\r\n\f\v]', '', value), validate=True)
        if not data:
            raise ValueError()
        return data
    except ValueError:
        raise ValueError('Invalid secret: APPLE_CERT_BASE64') from None


def preflight(env):
    missing = [name for name in REQUIRED if not env.get(name, '').strip()]
    if missing:
        raise ValueError('Missing secrets: ' + ', '.join(missing))
    decode_certificate(env['APPLE_CERT_BASE64'])
    for name, size in [('SPARKLE_PUBLIC_ED_KEY', 32)]:
        try:
            data = base64.b64decode(env[name], validate=True)
            if not data or (size and len(data) != size):
                raise ValueError()
        except ValueError:
            raise ValueError('Invalid secret: ' + name) from None
    if not re.fullmatch(r'[A-Z0-9]{10}', env['APPLE_TEAM_ID']):
        raise ValueError('Invalid secret: APPLE_TEAM_ID')


def check_archive(path):
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if any(part.startswith('._') or part == '__MACOSX' for part in name.split('/')):
                raise ValueError('AppleDouble metadata in release archive')


if __name__ == '__main__':
    try:
        if sys.argv[1] == 'preflight':
            preflight(os.environ)
        elif sys.argv[1] == 'decode-certificate':
            data = decode_certificate(os.environ.get('APPLE_CERT_BASE64', ''))
            with open(sys.argv[2], 'wb') as output:
                output.write(data)
        elif sys.argv[1] == 'archive':
            check_archive(sys.argv[2])
        else:
            raise ValueError('Unknown check')
    except ValueError as error:
        sys.exit(str(error))
