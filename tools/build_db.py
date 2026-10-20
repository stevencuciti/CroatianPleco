"""Build the app's offline SQLite dictionary from extracted Wiktionary entries + AI enrichment.

Usage: python -I tools/build_db.py data/work data/enrich app/assets/dict.db

Schema (read by hr.rjecnik.data.DictionaryDb — keep in sync with docs/APP_SPEC.md):
  meta(key TEXT PRIMARY KEY, value TEXT)
  entries(id INTEGER PRIMARY KEY, headword TEXT, accented TEXT, pos TEXT, gram TEXT, dialect TEXT,
          freq INTEGER, gloss TEXT, kaj TEXT, data BLOB)   -- data = zlib-deflated UTF-8 JSON
  hr_index(term TEXT, entry_id INTEGER, kind INTEGER, form TEXT, info TEXT)
  en_index(term TEXT, entry_id INTEGER, weight INTEGER)
"""
import collections
import glob
import json
import os
import re
import sqlite3
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hrtext import fold, fold_d, strip_accents, en_norm, en_keywords  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')

KIND_HEAD, KIND_KAJ, KIND_FORM, KIND_ALT = 0, 1, 2, 3
DB_VERSION = 1


def load_enrichment(enrich_dir):
    """Generated objects, overridden by reviewer corrections. Returns {id: obj}, stats."""
    out, stats = {}, collections.Counter()
    for sub, key in (('out', 'gen'), ('review', 'rev'), ('fix', 'fix')):
        for path in sorted(glob.glob(os.path.join(enrich_dir, sub, '*.jsonl'))):
            if os.path.basename(path).startswith('pilot'):
                continue
            for n, line in enumerate(open(path, encoding='utf-8'), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    eid = int(obj['id'])
                except (ValueError, KeyError, TypeError):
                    stats[f'bad_{key}_lines'] += 1
                    continue
                if key in ('rev', 'fix') and eid in out:
                    stats[key + '_overrides'] += 1
                out[eid] = obj
                stats[f'{key}_objects'] += 1
    return out, stats


def clean_text(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def clean_examples(raw):
    exs = []
    for x in raw or []:
        if isinstance(x, (list, tuple)) and len(x) >= 2 and clean_text(x[0]):
            exs.append({'hr': strip_accents(clean_text(x[0])), 'en': clean_text(x[1]), 'src': 'ai'})
        elif isinstance(x, dict) and clean_text(x.get('hr') or x.get('t')):
            exs.append({'hr': strip_accents(clean_text(x.get('hr') or x.get('t'))),
                        'en': clean_text(x.get('en')), 'src': 'ai'})
    return exs[:4]


def clean_kaj(k):
    if not isinstance(k, dict):
        return None
    w = clean_text(k.get('w'))
    if not w:
        return None
    out = {'w': strip_accents(w), 'c': k.get('c') if k.get('c') in ('h', 'm', 'l') else 'm', 'src': 'ai'}
    if clean_text(k.get('n')):
        out['n'] = clean_text(k.get('n'))
    ex = k.get('ex')
    if isinstance(ex, (list, tuple)) and len(ex) >= 2 and clean_text(ex[0]):
        out['ex'] = {'t': strip_accents(clean_text(ex[0])), 'en': clean_text(ex[1])}
    elif isinstance(ex, (list, tuple)) and ex and isinstance(ex[0], (list, tuple)) and len(ex[0]) >= 2:
        out['ex'] = {'t': strip_accents(clean_text(ex[0][0])), 'en': clean_text(ex[0][1])}
    return out


PAREN = re.compile(r'\([^()]*\)')


def gloss_phrases(gloss):
    """Split an English gloss into searchable phrases: 'to go, walk (on foot)' -> ['to go', 'go', 'walk']."""
    g = gloss
    for _ in range(3):
        g = PAREN.sub(' ', g)
    g = re.sub(r'[“”"]', ' ', g)
    phrases = []
    for part in re.split(r'[;,]', g):
        p = en_norm(part)
        if not p or len(p) > 40:
            continue
        phrases.append(p)
        for art in ('to ', 'a ', 'an ', 'the '):
            if p.startswith(art) and len(p) > len(art) + 1:
                phrases.append(p[len(art):])
    return phrases


def short_gloss(senses):
    parts, total = [], 0
    for s in senses:
        g = s['g']
        if g.lower().startswith(('used ', 'alternative form', 'alternative spelling')) and parts:
            continue
        if len(g) > 70:
            g = g[:67].rstrip() + '…'
        parts.append(g)
        total += len(g)
        if total > 110 or len(parts) >= 4:
            break
    return '; '.join(parts)


def table_forms(tables):
    """(plain form, description) pairs from the inflection tables."""
    out = []
    for t in tables:
        cols = t['cols']
        for r in t['rows']:
            for ci, cell in enumerate(r[1:], 1):
                col = cols[ci] if ci < len(cols) else ''
                # participle cells look like 'bio / bijen (m), bila (f)': gender groups first, then variants
                for group in cell.split(', '):
                    m = re.search(r' \(([mfn])\)$', group.strip())
                    gender = m.group(1) if m else ''
                    for piece in re.sub(r' \([mfn]\)$', '', group.strip()).split(' / '):
                        piece = piece.strip()
                        if not piece or piece == '—' or ' ' in piece:
                            continue
                        out.append((strip_accents(piece), describe(t['title'], r[0], col, gender)))
    return out


ABBR = {'Nominative': 'nom.', 'Genitive': 'gen.', 'Dative': 'dat.', 'Accusative': 'acc.', 'Vocative': 'voc.',
        'Locative': 'loc.', 'Instrumental': 'ins.', 'Singular': 'sg.', 'Plural': 'pl.', 'singular': 'sg.',
        'plural': 'pl.', 'Present': 'present', 'Aorist': 'aorist', 'Imperfect': 'imperfect',
        'Imperative': 'imperative', 'Comparative': 'comparative', 'Superlative': 'superlative',
        'Definite': 'def.', 'Indefinite': 'indef.', 'Positive': ''}


def describe(title, row, col, gender=''):
    """Short grammatical description of a table cell, e.g. 'gen. sg.', 'present 1st sg.', 'f sg. def.'."""
    if title == 'Non-finite forms':
        base = row.replace(' (sg.)', '').replace(' (pl.)', '').lower()
        num = 'sg.' if '(sg.)' in row else 'pl.' if '(pl.)' in row else ''
        return ' '.join(x for x in (base, gender, num) if x)
    if title == 'Declension':
        return f"{ABBR.get(row, row)} {ABBR.get(col, col)}"
    if ' — ' in title:  # adjective: 'Positive · Indefinite — singular'
        head, number = title.split(' — ', 1)
        quals = [ABBR.get(x, x.lower()) for x in head.split(' · ')]
        return ' '.join(x for x in [ABBR.get(row, row), col, ABBR.get(number, number)] + quals if x)
    # verb tense table
    person = row.replace('1st', '1st').replace('2nd', '2nd').replace('3rd', '3rd')
    return f"{ABBR.get(title, title.lower())} {person} {ABBR.get(col, col)}"


def build(work_dir, enrich_dir, db_path):
    entries = [json.loads(l) for l in open(os.path.join(work_dir, 'entries.jsonl'), encoding='utf-8')]
    formmap = [json.loads(l) for l in open(os.path.join(work_dir, 'formmap.jsonl'), encoding='utf-8')]
    enrich, stats = load_enrichment(enrich_dir)

    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = sqlite3.connect(db_path)
    db.executescript('''
        PRAGMA page_size = 4096;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE entries(id INTEGER PRIMARY KEY, headword TEXT NOT NULL, accented TEXT, pos TEXT, gram TEXT,
                             dialect TEXT, freq INTEGER, gloss TEXT, kaj TEXT, data BLOB);
        CREATE TABLE hr_index(term TEXT NOT NULL, entry_id INTEGER NOT NULL, kind INTEGER NOT NULL, form TEXT, info TEXT);
        CREATE TABLE en_index(term TEXT NOT NULL, entry_id INTEGER NOT NULL, weight INTEGER NOT NULL);
    ''')

    by_word = collections.defaultdict(list)
    for e in entries:
        by_word[(e['word'], e['pos'])].append(e['id'])
        by_word[(e['word'], None)].append(e['id'])

    hr_rows, en_rows, entry_rows = [], [], []
    seen_hr = set()

    def add_hr(term_src, eid, kind, form, info=''):
        for term in {fold(term_src), fold_d(term_src)}:
            if not term:
                continue
            key = (term, eid, kind)
            if key in seen_hr:
                continue
            seen_hr.add(key)
            hr_rows.append((term, eid, kind, form, info))

    for e in entries:
        eid = e['id']
        en = enrich.get(eid, {})
        freq = en.get('f')
        try:
            freq = max(1, min(5, int(freq)))
        except (TypeError, ValueError):
            freq = 2 if e['pos'] != 'name' else 1
            stats['no_enrichment'] += 1
        ai_ex = clean_examples(en.get('ex'))
        kaj = clean_kaj(en.get('k'))
        wikt_kaj = [a['form'] for a in e['alt'] if 'Kajkavian' in a.get('label', '')]
        std = clean_text(en.get('std')) if e['dialect'] != 'std' else ''

        data = {
            'w': e['word'], 'a': e['acc'], 'p': e['pos'], 'g': e['gram'], 'd': e['dialect'],
            'ipa': e['ipa'], 'hy': e['hyph'],
            's': [{k: v for k, v in s.items() if k != 'dialect' and v} for s in e['senses']],
            'ax': ai_ex,
            't': e['tables'],
            'alt': e['alt'],
            'rel': e['rel'],
            'syn': e['syn'], 'ant': e['ant'], 'der': e['derived'], 'relw': e['related'],
            'ety': e['ety'],
        }
        if std:
            data['std'] = strip_accents(std)
        if kaj:
            data['k'] = kaj
        if wikt_kaj:
            data['kw'] = wikt_kaj
        data = {k: v for k, v in data.items() if v not in ('', [], {}, None)}
        blob = zlib.compress(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 9)

        kaj_display = kaj['w'] if kaj else (', '.join(wikt_kaj) if wikt_kaj else '')
        entry_rows.append((eid, e['word'], e['acc'], e['pos'], e['gram'], e['dialect'], freq,
                           short_gloss(e['senses']), kaj_display, blob))

        # Croatian / Kajkavian search keys
        add_hr(e['word'], eid, KIND_HEAD, e['word'])
        for w in wikt_kaj:
            add_hr(w, eid, KIND_KAJ, w, 'Kajkavian')
        if kaj:
            for w in re.split(r'[,;/]', kaj['w']):
                w = w.strip()
                if w and fold(w) != fold(e['word']):
                    add_hr(w, eid, KIND_KAJ, w, 'Međimurje Kajkavian')
        if std:
            for w in re.split(r'[,;/]', data.get('std', '')):
                if w.strip():
                    add_hr(w.strip(), eid, KIND_ALT, w.strip(), 'standard equivalent')
        for a in e['alt']:
            if 'Kajkavian' not in a.get('label', ''):
                add_hr(a['form'], eid, KIND_ALT, strip_accents(a['form']), a.get('label') or 'variant')
        descs = collections.OrderedDict()
        for form, desc in table_forms(e['tables']):
            if fold(form) == fold(e['word']):
                continue
            descs.setdefault(form, [])
            if desc not in descs[form]:
                descs[form].append(desc)
        for form, ds in descs.items():
            add_hr(form, eid, KIND_FORM, form, '; '.join(ds[:2])[:60])

        # English search keys
        for si, s in enumerate(e['senses'][:10]):
            g = s['g']
            if g.lower().startswith(('alternative form of', 'alternative spelling of')):
                continue
            seen_en = set()
            for pi, p in enumerate(gloss_phrases(g)[:12]):
                if p not in seen_en:
                    seen_en.add(p)
                    en_rows.append((p, eid, 1000 - si * 40 - pi * 4))
            for kw in en_keywords(PAREN.sub(' ', g))[:12]:
                if kw not in seen_en:
                    seen_en.add(kw)
                    en_rows.append((kw, eid, 500 - si * 40))

    # inflected forms recorded on Wiktionary "form of" pages
    for m in formmap:
        targets = by_word.get((m['lemma'], m['pos'])) or by_word.get((m['lemma'], None)) or []
        for eid in targets[:3]:
            info = ' '.join(t for t in m['tags'] if t not in ('form-of',))
            add_hr(m['form'], eid, KIND_FORM, m['form'], info)

    db.executemany('INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?)', entry_rows)
    db.executemany('INSERT INTO hr_index VALUES (?,?,?,?,?)', hr_rows)
    db.executemany('INSERT INTO en_index VALUES (?,?,?)', en_rows)
    db.executescript('''
        CREATE INDEX hr_index_term ON hr_index(term);
        CREATE INDEX en_index_term ON en_index(term);
        CREATE INDEX entries_headword ON entries(headword);
    ''')
    with_ai = sum(1 for r in entry_rows if r[0] in enrich)
    meta = {
        'db_version': str(DB_VERSION),
        'entries': str(len(entry_rows)),
        'entries_enriched': str(with_ai),
        'source': 'Wiktionary (English edition) via kaikki.org, CC BY-SA 4.0; AI-generated examples and Kajkavian forms',
        'kajkavian_variety': 'Međimurje',
    }
    db.executemany('INSERT INTO meta VALUES (?,?)', meta.items())
    db.commit()
    db.execute('ANALYZE')
    db.commit()
    db.execute('VACUUM')
    db.close()
    stats.update({'entries': len(entry_rows), 'hr_index': len(hr_rows), 'en_index': len(en_rows),
                  'enriched': with_ai, 'db_bytes': os.path.getsize(db_path)})
    print(json.dumps(dict(stats), indent=1))


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], sys.argv[3])
