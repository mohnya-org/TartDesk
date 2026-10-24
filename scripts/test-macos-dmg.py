import base64
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('dmg', Path(__file__).with_name('macos-dmg.py'))
dmg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dmg)
TEAM = 'ABCDEFGHIJ'
FINGERPRINT = 'A' * 40
ENV = dict(APPLE_CERT_BASE64=base64.b64encode(b'fixture').decode(), APPLE_CERT_PASSWORD='fixture',
           APPLE_TEAM_ID=TEAM, APPLE_API_KEY_ID='fixture', APPLE_API_ISSUER_ID='fixture',
           APPLE_API_PRIVATE_KEY='-----BEGIN PRIVATE KEY-----\nfixture')


class DmgTests(unittest.TestCase):
    def test_required_secrets(self):
        with self.assertRaisesRegex(dmg.DistributionError, 'Missing secrets'):
            dmg.preflight({})
        dmg.preflight(ENV)

    def test_invalid_inputs_fail_without_echoing_secret_values(self):
        for key in ('APPLE_CERT_BASE64', 'APPLE_TEAM_ID', 'APPLE_API_PRIVATE_KEY'):
            with self.subTest(key=key), self.assertRaises(dmg.DistributionError) as raised:
                dmg.preflight(dict(ENV, **{key:'sensitive-invalid-value'}))
            self.assertNotIn('sensitive-invalid-value', str(raised.exception))

    def test_only_matching_developer_id_application_is_selected(self):
        valid=f'1) {FINGERPRINT} "Developer ID Application: Example ({TEAM})"'
        self.assertEqual(dmg.select_identity(valid, TEAM), FINGERPRINT)
        for wrong in (valid.replace('Application:', 'Installer:'), valid.replace('Developer ID Application:', 'Apple Distribution:'), valid.replace(TEAM,'XXXXXXXXXX'), valid+'\n'+valid.replace(FINGERPRINT,'B'*40)):
            with self.assertRaises(dmg.DistributionError):
                dmg.select_identity(wrong, TEAM)

    def test_raw_tool_errors_are_not_exposed(self):
        with patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'private', b'private')):
            with self.assertRaisesRegex(dmg.DistributionError, '^Signing failed$'):
                dmg.run(['security','fixture'],'Signing')

    def test_cleanup_refuses_unrelated_directory(self):
        with self.assertRaises(dmg.DistributionError):
            dmg.cleanup('/tmp/unrelated')

    def exercise_create(self, status='Accepted'):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            app=root/'Test.app'
            (app/'Contents').mkdir(parents=True)
            info={'CFBundleIdentifier':'org.test.app','CFBundleVersion':'42','CFBundleShortVersionString':'1.2.3'}
            (app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
            archive=root/'Test-1.2.3.dmg'
            calls=[]
            def fake_run(args, stage, **kwargs):
                args=list(map(str,args)); calls.append(args)
                out=b''
                if args[:2]==['security','find-identity']:
                    out=f'1) {FINGERPRINT} "Developer ID Application: Example ({TEAM})"'.encode()
                elif args[:2]==['security','list-keychains']:
                    out=b'"/existing/login.keychain-db"'
                elif args[0]=='ditto':
                    shutil.copytree(args[1],args[2])
                elif args[:2]==['hdiutil','create']:
                    Path(args[-1]).write_bytes(b'disk image fixture')
                elif args[:3]==['xcrun','notarytool','submit']:
                    out=json.dumps({'status':status}).encode()
                elif args[:2]==['hdiutil','attach']:
                    mount=Path(args[args.index('-mountpoint')+1])
                    shutil.copytree(app,mount/app.name)
                    (mount/'Applications').symlink_to('/Applications')
                return subprocess.CompletedProcess(args,0,out,b'')
            with patch.dict(os.environ, dict(ENV, RUNNER_TEMP=str(root), GITHUB_ENV=''), clear=True), patch.object(dmg, 'run', side_effect=fake_run):
                if status!='Accepted':
                    with self.assertRaisesRegex(dmg.DistributionError, 'not Accepted'):
                        dmg.create(app,archive)
                    self.assertFalse(archive.with_suffix('.dmg.sha256').exists())
                    self.assertFalse(any(c[:3]==['xcrun','stapler','staple'] for c in calls))
                else:
                    dmg.create(app,archive)
                    self.assertTrue(archive.with_suffix('.dmg.sha256').is_file())
                    self.assertIn(['security','list-keychains','-d','user','-s','/existing/login.keychain-db',next(c[-1] for c in calls if c[:2]==['security','create-keychain'])],calls)
                    self.assertFalse(any(c[:2]==['security','default-keychain'] for c in calls))
            self.assertEqual(list(root.glob('macos-dmg-*')),[])

    def test_full_pipeline_validates_and_preserves_other_keychains(self):
        self.exercise_create()

    def test_notary_rejection_stops_distribution(self):
        self.exercise_create('Invalid')

    def test_layout_rejects_wrong_version_or_missing_link(self):
        with tempfile.TemporaryDirectory() as directory:
            mount=Path(directory)
            app=mount/'Test.app/Contents'; app.mkdir(parents=True)
            info={'CFBundleIdentifier':'a','CFBundleVersion':'1','CFBundleShortVersionString':'1.0.0'}
            (app/'Info.plist').write_bytes(plistlib.dumps(info))
            with self.assertRaises(dmg.DistributionError): dmg.verify_layout(mount,'Test.app',info)
            (mount/'Applications').symlink_to('/Applications')
            dmg.verify_layout(mount,'Test.app',info)
            with self.assertRaises(dmg.DistributionError): dmg.verify_layout(mount,'Test.app',dict(info,CFBundleVersion='2'))


if __name__=='__main__':
    unittest.main()
