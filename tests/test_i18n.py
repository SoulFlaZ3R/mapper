"""Every language has the same keys and every key used by the app exists."""
import json
import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'
LANGUAGES = ('it', 'en', 'de', 'fr', 'es')


def used_keys():
    qml = (SRC / 'qml' / 'Main.qml').read_text(encoding='utf-8')
    py = (SRC / 'backend.py').read_text(encoding='utf-8')
    keys = set(re.findall(r'\bt\("([a-z_]+)"\)', qml)) | set(re.findall(r'\bfmt\("([a-z_]+)"', qml))
    keys |= set(re.findall(r'\["[^"]+", "([a-z_]+)"\]', qml))  # guide shortcut table
    keys |= {'theme_' + theme for theme in re.search(r'property var themes: \[([^\]]+)\]', qml).group(1).replace('"', '').replace(' ', '').split(',')}
    keys |= set(re.findall(r"_status\('([a-z_]+)'", py)) | set(re.findall(r"UserError\('([a-z_]+)'\)", py))
    keys |= set(re.findall(r"_translations\['([a-z_]+)'\]", py))
    keys |= set(re.findall(r"_part\('([a-z_]+)'", py))
    return keys


class TranslationTests(unittest.TestCase):
    def load(self, language):
        return json.loads((SRC / 'Languages' / f'{language}.json').read_text(encoding='utf-8'))

    def test_languages_share_keys_and_placeholders(self):
        english = self.load('en')
        for language in LANGUAGES:
            data = self.load(language)
            self.assertEqual(list(data), list(english), language)
            for key, text in english.items():
                self.assertEqual(set(re.findall(r'{\w+}', data[key])), set(re.findall(r'{\w+}', text)), (language, key))

    def test_used_keys_exist_and_none_are_orphaned(self):
        keys, used = set(self.load('en')), used_keys()
        self.assertEqual(sorted(used - keys), [], 'missing translations')
        self.assertEqual(sorted(keys - used), [], 'unused translations')


if __name__ == '__main__':
    unittest.main()
