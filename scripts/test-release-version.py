import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('release_version', Path(__file__).with_name('release-version.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def release(tag, draft=False, prerelease=False):
    return dict(tag_name=tag, draft=draft, prerelease=prerelease)


class VersionTests(unittest.TestCase):
    def test_numeric_order_and_patch_increment(self):
        result = module.select_version({'v1.9.9': 'a', 'v1.10.0': 'b'}, [release('v1.9.9'), release('v1.10.0')], 'c')
        self.assertEqual(result['version'], '1.10.1')

    def test_first_release(self):
        self.assertEqual(module.select_version({}, [], 'a')['version'], '0.0.1')

    def test_manual_minor_release(self):
        self.assertEqual(module.select_version({'v1.2.3': 'a'}, [release('v1.2.3')], 'b', '1.3.0')['version'], '1.3.0')

    def test_retry_published_commit_is_noop(self):
        self.assertEqual(module.select_version({'v1.2.3': 'a'}, [release('v1.2.3')], 'a')['should_release'], 'false')

    def test_retry_orphan_tag_and_draft(self):
        for releases in ([], [release('v1.2.4', draft=True)]):
            self.assertEqual(module.select_version({'v1.2.4': 'a'}, releases, 'a')['tag'], 'v1.2.4')

    def test_other_commits_orphan_tags_are_reserved(self):
        self.assertEqual(module.select_version({'v1.2.3': 'a', 'v1.2.4': 'b'}, [release('v1.2.3')], 'c')['version'], '1.2.5')

    def test_beta_and_unrelated_tags_do_not_raise_stable_version(self):
        result = module.select_version({'v1.2.3': 'a', 'v9.0.0-beta.1': 'b', 'test': 'c'}, [release('v1.2.3'), release('v9.0.0-beta.1', prerelease=True)], 'd')
        self.assertEqual(result['version'], '1.2.4')

    def test_invalid_or_older_versions_and_collisions_fail(self):
        for version in ('v1.2.4', '1.2', '1.02.4', '1.3.0-beta.1', '1.1.0', '1.2.3'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                module.select_version({'v1.2.3': 'a'}, [release('v1.2.3')], 'b', version)

    def test_stale_pending_tag_cannot_replace_newer_release(self):
        with self.assertRaises(ValueError):
            module.select_version({'v1.2.3': 'a', 'v1.2.4': 'b'}, [release('v1.2.4')], 'a')


if __name__ == '__main__':
    unittest.main()
