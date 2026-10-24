"""Exercise publication/retry behavior with isolated git and GitHub stand-ins."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
root=pathlib.Path(os.environ['FAKE_STATE'])
args=sys.argv[1:]
with (root/'calls').open('a') as out:
    out.write(json.dumps([pathlib.Path(sys.argv[0]).name, *args])+'\n')
state=json.loads((root/'state.json').read_text())
name=pathlib.Path(sys.argv[0]).name
if name=='git':
    if args[:2]==['rev-parse','HEAD']: print('commit-a')
    elif args[0]=='show-ref': sys.exit(0 if state['tag'] else 1)
    elif args[0]=='rev-list': print(state['tag'])
    elif args[0]=='tag': state['tag']=args[2]
else:
    if args[0]=='api':
        print(json.dumps([[] if state['release']=='missing' else [{'tag_name':'v1.2.4','draft':state['release']=='draft','prerelease':False}]]))
    elif args[:2]==['release','view']:
        if state.get('fail_notes'): sys.exit(1)
        print(json.dumps({'body': state.get('body', '## Changes\n- Fix & improve <audio>'), 'url':'https://github.com/owner/app/releases/tag/v1.2.4'}))
    elif args[:2]==['release','create']: state['release']='draft'
    elif args[:2]==['release','upload'] and state.get('fail_upload'): sys.exit(1)
    elif args[:2]==['release','edit']: state['release']='published'
(root/'state.json').write_text(json.dumps(state))
'''


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'bin').mkdir()
        (self.root/'dist').mkdir()
        for tool in ('git', 'gh'):
            p=self.root/'bin'/tool
            p.write_text(FAKE)
            p.chmod(0o755)
        for name in ('app.zip','app.zip.sha256','appcast.xml','app.dmg','app.dmg.sha256'):
            (self.root/'dist'/name).write_text('fixture')
        (self.root/'dist/appcast.xml').write_text('<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel><item><sparkle:version>1.2.4</sparkle:version><enclosure url="https://github.com/owner/app/archive.zip" length="42" sparkle:edSignature="unchanged-signature" /></item></channel></rss>')
        self.env=dict(os.environ, FAKE_STATE=str(self.root), PATH=str(self.root/'bin')+os.pathsep+os.environ['PATH'], TAG='v1.2.4', GITHUB_REPOSITORY='owner/app', ZIP_PATH=str(self.root/'dist/app.zip'), CHECKSUM_PATH=str(self.root/'dist/app.zip.sha256'))
        self.env['DMG_PATH']=str(self.root/'dist/app.dmg')
        self.save(tag=None, release='missing')

    def save(self, **state):
        (self.root/'state.json').write_text(json.dumps(state))

    def load(self):
        return json.loads((self.root/'state.json').read_text())

    def run_script(self):
        return subprocess.run(['bash',str(Path(__file__).with_name('publish-release.sh').resolve())], cwd=self.root, env=self.env, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in (self.root/'calls').read_text().splitlines()]

    def test_publish_only_after_all_assets_upload(self):
        self.assertEqual(self.run_script().returncode,0)
        self.assertEqual(self.load()['release'],'published')
        commands=[c[1:3] for c in self.calls() if c[0]=='gh']
        self.assertEqual(commands[-4:],[['release','create'],['release','view'],['release','upload'],['release','edit']])
        upload=next(c for c in self.calls() if c[:3]==['gh','release','upload'])
        self.assertIn('dist/appcast.xml',upload)
        self.assertIn(self.env['ZIP_PATH'],upload)
        self.assertIn(self.env['CHECKSUM_PATH'],upload)
        self.assertIn(self.env['DMG_PATH'],upload)
        self.assertIn(self.env['DMG_PATH']+'.sha256',upload)

    def test_upload_failure_stays_draft_then_retry_finishes(self):
        self.save(tag=None,release='missing',fail_upload=True)
        self.assertNotEqual(self.run_script().returncode,0)
        state=self.load()
        self.assertEqual(state['release'],'draft')
        state['fail_upload']=False
        self.save(**state)
        self.assertEqual(self.run_script().returncode,0)
        self.assertEqual(self.load()['release'],'published')
        self.assertEqual(sum(c[:3]==['gh','release','create'] for c in self.calls()),1)

    def test_release_body_is_embedded_without_changing_enclosure(self):
        import xml.etree.ElementTree as ET
        ns = '{http://www.andymatuschak.org/xml-namespaces/sparkle}'
        self.assertEqual(self.run_script().returncode, 0)
        item = ET.parse(self.root/'dist/appcast.xml').find('./channel/item')
        self.assertEqual(item.find('description').text, '## Changes\n- Fix & improve <audio>')
        self.assertEqual(item.find('description').get(ns+'format'), 'markdown')
        self.assertEqual(item.find('enclosure').get(ns+'edSignature'), 'unchanged-signature')
        self.assertEqual(item.find('enclosure').get('length'), '42')
        self.assertEqual(item.find('enclosure').get('url'), 'https://github.com/owner/app/archive.zip')
        self.assertEqual(item.find(ns+'version').text, '1.2.4')

    def test_retry_uses_existing_draft_notes(self):
        self.save(tag='commit-a', release='draft', body='Custom release notes')
        self.assertEqual(self.run_script().returncode, 0)
        self.assertIn('Custom release notes', (self.root/'dist/appcast.xml').read_text())
        self.assertFalse(any(c[:3]==['gh','release','create'] for c in self.calls()))

    def test_notes_failure_leaves_release_draft(self):
        self.save(tag=None, release='missing', fail_notes=True)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.load()['release'], 'draft')
        self.assertFalse(any(c[:3]==['gh','release','upload'] for c in self.calls()))

    def test_empty_notes_have_honest_fallback(self):
        self.save(tag='commit-a', release='draft', body=None)
        self.assertEqual(self.run_script().returncode, 0)
        self.assertIn('No release notes were provided', (self.root/'dist/appcast.xml').read_text())

    def test_published_release_is_immutable(self):
        self.save(tag='commit-a',release='published')
        self.assertEqual(self.run_script().returncode,0)
        self.assertFalse(any(c[:3]==['gh','release','upload'] for c in self.calls()))

    def test_conflicting_tag_is_rejected(self):
        self.save(tag='commit-b',release='missing')
        self.assertNotEqual(self.run_script().returncode,0)
        self.assertFalse(any(c[0]=='gh' for c in self.calls()))

    def test_missing_dmg_creates_no_tag(self):
        (self.root/'dist/app.dmg').unlink()
        self.assertNotEqual(self.run_script().returncode,0)
        self.assertFalse((self.root/'calls').exists())

    def test_missing_asset_creates_no_tag(self):
        (self.root/'dist/appcast.xml').unlink()
        self.assertNotEqual(self.run_script().returncode,0)
        self.assertFalse((self.root/'calls').exists())


if __name__=='__main__':
    unittest.main()
