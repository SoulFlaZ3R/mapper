"""Contrasto WCAG 2.x dei temi: testo normale almeno 4,5:1 su ogni sfondo usato.
WCAG 2.x contrast of the themes: normal text at least 4.5:1 on every background it is used on."""
import re
import unittest
from pathlib import Path

QML = Path(__file__).resolve().parents[1] / 'src' / 'qml' / 'Main.qml'
# (testo, sfondo) usati dall'interfaccia / (text, background) pairs used by the interface
PAIRS = [('ink', 'bg'), ('ink', 'surface'), ('ink', 'inset'), ('ink', 'selection'), ('muted', 'bg'), ('muted', 'surface'),
         ('muted', 'inset'), ('muted', 'selection'), ('onAccent', 'accent'), ('danger', 'surface'), ('danger', 'bg'),
         ('accent', 'surface')]


def palettes():
    text = QML.read_text(encoding='utf-8')
    block = text[text.index('readonly property var palettes'):text.index('readonly property var pal:')]
    return {name: dict(re.findall(r'(\w+): "#([0-9a-fA-F]{6})"', body))
            for name, body in re.findall(r'(\w+):\s*\{([^}]*)\}', block)}


def luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ContrastTests(unittest.TestCase):
    def test_every_theme_meets_wcag_aa_for_normal_text(self):
        themes = palettes()
        self.assertEqual(sorted(themes), ['blue', 'dark', 'light', 'red'])
        for name, colors in themes.items():
            for text, background in PAIRS:
                ratio = contrast(colors[text], colors[background])
                self.assertGreaterEqual(ratio, 4.5, f'{name}: {text} on {background} = {ratio:.2f}')


if __name__ == '__main__':
    unittest.main()
