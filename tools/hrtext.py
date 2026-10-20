"""Croatian text helpers shared by the data pipeline.

The same folding rules are re-implemented in the app (TextNorm.java); keep them in sync.
"""
import re
import unicodedata

# Combining marks Wiktionary uses for tonal accents and vowel length.
_ACCENT_MARKS = {'̀', '́', '̂', '̄', '̆', '̏', '̑', '̥'}
_ACCENT_BASES = set('aeiouAEIOUrRə')  # vowels, syllabic r, schwa


def strip_accents(s):
    """Remove tonal accents/length marks but keep č ć š ž đ (ć is c + acute in NFD)."""
    out = []
    for ch in unicodedata.normalize('NFD', s):
        if ch in _ACCENT_MARKS and out and out[-1] in _ACCENT_BASES:
            continue
        out.append(ch)
    return unicodedata.normalize('NFC', ''.join(out))


_FOLD = str.maketrans({'č': 'c', 'ć': 'c', 'š': 's', 'ž': 'z', 'đ': 'dj',
                       'Č': 'c', 'Ć': 'c', 'Š': 's', 'Ž': 'z', 'Đ': 'dj'})


def fold(s):
    """Search key: accents stripped, lowercased, č/ć→c, š→s, ž→z, đ→dj, whitespace collapsed."""
    s = strip_accents(s).lower().translate(_FOLD)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[’'`]", '', s)
    s = re.sub(r'[^0-9a-zə \-]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def fold_d(s):
    """Alternate key where đ folds to plain d (people often type 'dak' for 'đak')."""
    return fold(s.replace('đ', 'd').replace('Đ', 'd'))


def is_cyrillic(s):
    return any('Ѐ' <= ch <= 'ӿ' for ch in s)


_EN_STOP = {'a', 'an', 'the', 'to', 'of', 'or', 'and', 'in', 'on', 'for', 'with', 'by', 'as', 'at',
            'from', 'into', 'be', 'is', 'something', 'someone', 'somebody', 'one', 'oneself', 'etc',
            'e', 'g', 'i', 'eg', 'ie', 'sth', 'sb', 'who', 'which', 'that', 'its', 'their', 'his', 'her'}


def en_norm(s):
    s = unicodedata.normalize('NFKD', s.lower())
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[’']", "'", s)
    s = re.sub(r"[^a-z0-9' \-]+", ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def en_tokens(s):
    return [t.strip("'-") for t in en_norm(s).replace('-', ' ').split() if t.strip("'-")]


def en_keywords(s):
    return [t for t in en_tokens(s) if t not in _EN_STOP and len(t) > 1]
