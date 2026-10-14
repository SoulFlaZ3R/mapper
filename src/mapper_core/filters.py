"""
Esclusioni in stile .gitignore (sottoinsieme documentato) / .gitignore-style exclusions (documented subset).

Supportato / Supported:
  - righe vuote e commenti '#' ignorati; '\\#' e '\\!' per un nome che inizia con # o !
  - '*' (non attraversa '/'), '?', classi '[abc]' e '[!abc]', '**' (zero o più cartelle)
  - '/' finale: solo cartelle; '/' iniziale o interno: percorso relativo alla radice mappata
  - senza '/': confronto con il nome a qualsiasi profondità
  - '!pattern': reinclude; vince l'ultima regola che corrisponde
Differenze da git / Differences from git:
  - confronto senza distinzione di maiuscole (come il file system di Windows)
  - una cartella esclusa non viene letta, quindi '!' non può reincludere qualcosa al suo interno (come git)
  - un solo elenco di regole (niente file .gitignore annidati letti dal disco)
"""
import re

# Cartelle tecniche escluse dal preset / Technical folders excluded by the preset
TECHNICAL = ('.git/', '.svn/', '.hg/', 'node_modules/', '__pycache__/', '.venv/', '.pytest_cache/',
             '.mypy_cache/', '.ruff_cache/', '.tox/', '.idea/', '.vs/', '$RECYCLE.BIN/',
             'System Volume Information/', 'Thumbs.db')


def _translate(glob):
    """Glob (con '/') → regex / Glob (with '/') → regex."""
    out, i, n = [], 0, len(glob)
    while i < n:
        c = glob[i]
        if c == '*':
            if glob.startswith('**/', i):
                out.append('(?:.*/)?')
                i += 3
                continue
            if glob.startswith('**', i):
                out.append('.*')
                i += 2
                continue
            out.append('[^/]*')
        elif c == '?':
            out.append('[^/]')
        elif c == '[':
            end = glob.find(']', i + 2)
            if end < 0:
                out.append(re.escape(c))
            else:
                body = glob[i + 1:end]
                negate = body[:1] in ('!', '^')
                body = body[1:] if negate else body
                out.append('[' + ('^' if negate else '') + body.replace('\\', '\\\\') + ']')
                i = end + 1
                continue
        elif c == '\\' and i + 1 < n:
            out.append(re.escape(glob[i + 1]))
            i += 2
            continue
        else:
            out.append(re.escape(c))
        i += 1
    return ''.join(out)


class Rule:
    __slots__ = ('pattern', 'negate', 'dir_only', 'anchored', 'regex')

    def __init__(self, pattern):
        self.pattern = pattern
        text = pattern
        self.negate = text.startswith('!')
        if self.negate:
            text = text[1:]
        elif text.startswith(('\\!', '\\#')):
            text = text[1:]
        self.dir_only = text.endswith('/')
        text = text.rstrip('/')
        self.anchored = '/' in text
        text = text.lstrip('/')
        self.regex = re.compile(_translate(text), re.IGNORECASE | re.DOTALL)


class Excludes:
    """
    Regole compilate. excluded(rel, name, is_dir): rel = percorso relativo con '/'.
    Compiled rules. excluded(rel, name, is_dir): rel = relative path with '/'.
    """

    def __init__(self, patterns=()):
        self.patterns = []
        self.rules = []
        for line in patterns:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            self.patterns.append(line)
            self.rules.append(Rule(line))

    @classmethod
    def from_text(cls, text, technical=False):
        """Una regola per riga, più il preset tecnico se richiesto / One rule per line, plus the preset."""
        lines = (list(TECHNICAL) if technical else []) + text.replace('\r', '').split('\n')
        return cls(lines)

    def __bool__(self):
        return bool(self.rules)

    def excluded(self, rel, name, is_dir):
        result = False
        for rule in self.rules:
            if rule.dir_only and not is_dir:
                continue
            if rule.regex.fullmatch(rel if rule.anchored else name):
                result = not rule.negate
        return result
