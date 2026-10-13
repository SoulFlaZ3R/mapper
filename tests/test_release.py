"""Release helper: version bumps, CHANGELOG sections and the version mentions in the documents."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build'))
import release  # noqa: E402

CHANGELOG = '''# Changelog

## [Unreleased]

### Fixed

- Something

## [1.5.0] - 2026-10-14

### Added

- First

[Unreleased]: https://github.com/SoulFlaZ3R/mapper/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/SoulFlaZ3R/mapper/releases/tag/v1.5.0
'''


class ReleaseTests(unittest.TestCase):
    def test_next_version(self):
        self.assertEqual(release.next_version('1.5.0', 'patch'), '1.5.1')
        self.assertEqual(release.next_version('1.5.3', 'minor'), '1.6.0')
        self.assertEqual(release.next_version('1.9.2', 'major'), '2.0.0')
        self.assertEqual(release.next_version('1.5.0', '1.7.0'), '1.7.0')
        with self.assertRaises(release.ReleaseError):
            release.next_version('1.5.0', 'v1.6')

    def test_changelog_release_moves_unreleased_and_links(self):
        text = release.changelog_release(CHANGELOG, '1.5.1', '2026-11-02')
        self.assertIn('## [Unreleased]\n\n## [1.5.1] - 2026-11-02\n\n### Fixed', text)
        self.assertEqual(release.section(text, '1.5.1'), '### Fixed\n\n- Something')
        self.assertEqual(release.section(text, '1.5.0'), '### Added\n\n- First')
        self.assertIn('[Unreleased]: https://github.com/SoulFlaZ3R/mapper/compare/v1.5.1...HEAD\n'
                      '[1.5.1]: https://github.com/SoulFlaZ3R/mapper/compare/v1.5.0...v1.5.1\n'
                      '[1.5.0]: https://github.com/SoulFlaZ3R/mapper/releases/tag/v1.5.0\n', text)
        self.assertEqual(text.count('[Unreleased]: '), 1)

    def test_first_release_and_crlf(self):
        first = '# Changelog\r\n\r\n## [Unreleased]\r\n\r\n- New\r\n\r\n[Unreleased]: https://example/commits/main\r\n'
        text = release.changelog_release(first, '1.5.0', '2026-10-14')
        self.assertNotIn('\n', text.replace('\r\n', ''))  # solo CRLF / CRLF only
        self.assertIn('[1.5.0]: https://github.com/SoulFlaZ3R/mapper/releases/tag/v1.5.0', text)
        self.assertEqual(release.section(text, '1.5.0'), '- New')

    def test_changelog_errors(self):
        with self.assertRaises(release.ReleaseError):
            release.changelog_release(CHANGELOG, '1.5.0', '2026-10-14')  # già rilasciata / already released
        empty = CHANGELOG.replace('### Fixed\n\n- Something\n\n', '')
        with self.assertRaises(release.ReleaseError):
            release.changelog_release(empty, '1.5.1', '2026-11-02')
        with self.assertRaises(release.ReleaseError):
            release.section(CHANGELOG, '1.4.0')

    def test_version_spots_match_once_in_the_repository(self):
        for name, pattern, replacement, required in release.VERSION_SPOTS:
            path = ROOT / name
            if not required and not path.exists():
                continue
            text = release.read(path)
            updated = release.set_version(text, pattern, replacement, '9.8.7', name)
            self.assertIn('9.8', updated, name)
            self.assertEqual(len(updated.splitlines()), len(text.splitlines()), name)

    def test_current_version_has_a_changelog_section(self):
        # La release usa questa sezione come testo / The release uses this section as its text
        changelog = release.read(ROOT / 'CHANGELOG.md')
        version = release.current_version()
        if version in release.released_versions(changelog):
            self.assertTrue(release.section(changelog, version))
        else:
            self.assertTrue(release.section(changelog, 'Unreleased'))


if __name__ == '__main__':
    unittest.main()
