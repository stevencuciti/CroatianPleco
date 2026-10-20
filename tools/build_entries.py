"""Extract Croatian (and Kajkavian / Chakavian) entries from the kaikki.org Serbo-Croatian dump.

Usage: python -I tools/build_entries.py data/raw/kaikki/kaikki-SerboCroatian.jsonl data/work

Writes:
  entries.jsonl  one normalised dictionary entry per line
  formmap.jsonl  inflected form -> lemma mappings taken from Wiktionary "form of" entries
  stats.json     counts for sanity checking
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hrtext import strip_accents, is_cyrillic  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')

CASES = ['nominative', 'genitive', 'dative', 'accusative', 'vocative', 'locative', 'instrumental']
CASE_LABEL = {'nominative': 'Nominative', 'genitive': 'Genitive', 'dative': 'Dative', 'accusative': 'Accusative',
              'vocative': 'Vocative', 'locative': 'Locative', 'instrumental': 'Instrumental'}
GENDERS = ['masculine', 'feminine', 'neuter']
GENDER_SHORT = {'masculine': 'm', 'feminine': 'f', 'neuter': 'n'}
DIALECT_TAGS = {'Kajkavian', 'Chakavian'}
NON_CROATIAN = {'Ekavian', 'Torlakian'}
SKIP_TABLE_TAGS = {'table-tags', 'inflection-template'}

LABEL_TAGS = ['Kajkavian', 'Chakavian', 'Croatia', 'Bosnia', 'regional', 'dialectal', 'colloquial', 'informal',
              'slang', 'vulgar', 'derogatory', 'archaic', 'obsolete', 'dated', 'rare', 'literary', 'figuratively',
              'transitive', 'intransitive', 'reflexive', 'ambitransitive', 'uncountable', 'diminutive',
              'augmentative', 'idiomatic', 'Ijekavian', 'Ikavian', 'historical', 'expressive']


def latin(words):
    out, seen = [], set()
    for w in words:
        if not w or is_cyrillic(w) or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def word_list(items, limit=40):
    return latin([i.get('word', '') for i in (items or []) if isinstance(i, dict)])[:limit]


def sense_labels(s):
    raw = (s.get('raw_glosses') or [''])[0]
    m = re.match(r'^\(([^)]*)\)\s*', raw)
    if m:
        return m.group(1)
    tags = [t for t in LABEL_TAGS if t in s.get('tags', [])]
    return ', '.join(tags)


def keep_sense(tags):
    if tags & DIALECT_TAGS:
        return True
    if tags & NON_CROATIAN:
        return False
    if ('Serbia' in tags or 'Montenegro' in tags) and 'Croatia' not in tags:
        return False
    return True


def uniq(seq):
    out = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


# ---------------------------------------------------------------- declension tables

def declension_tables(forms):
    rows = [f for f in forms if not (set(f['tags']) & SKIP_TABLE_TAGS) and f['form'] not in ('-', '')]
    if not rows:
        return []
    has_gender = any(set(f['tags']) & set(GENDERS) for f in rows)
    if not has_gender:
        cols = [n for n in ('singular', 'plural') if any(n in f['tags'] for f in rows)]
        if not cols:
            return []
        body = []
        for c in CASES:
            cells = []
            for n in cols:
                cells.append(' / '.join(uniq(f['form'] for f in rows if c in f['tags'] and n in f['tags'])))
            if any(cells):
                body.append([CASE_LABEL[c]] + cells)
        return [{'title': 'Declension', 'cols': [''] + [n.capitalize() for n in cols], 'rows': body}] if body else []

    groups = collections.OrderedDict()
    for f in rows:
        t = set(f['tags'])
        degree = next((d for d in ('positive', 'comparative', 'superlative') if d in t), '')
        definite = next((d for d in ('indefinite', 'definite') if d in t), '')
        groups.setdefault((degree, definite), []).append(f)
    tables = []
    for (degree, definite), fs in groups.items():
        title = ' · '.join(x.capitalize() for x in (degree, definite) if x) or 'Declension'
        for number in ('singular', 'plural'):
            body = []
            for c in CASES:
                cells = []
                for g in GENDERS:
                    sel = [f for f in fs if c in f['tags'] and g in f['tags'] and number in f['tags']]
                    # inanimate before animate for the masculine accusative
                    sel.sort(key=lambda f: 0 if 'inanimate' in f['tags'] else 1)
                    cells.append(' / '.join(uniq(f['form'] for f in sel)))
                if any(cells):
                    body.append([CASE_LABEL[c]] + cells)
            if body:
                tables.append({'title': f'{title} — {number}', 'cols': ['', 'm', 'f', 'n'], 'rows': body})
    return tables


# ---------------------------------------------------------------- conjugation tables

TENSES = [  # (key, title, tag test)
    ('present', 'Present', lambda t: 'present' in t and not t & {'participle', 'adverbial'}),
    ('future-i', 'Future I', lambda t: 'future-i' in t),
    ('future-ii', 'Future II', lambda t: 'future-ii' in t),
    ('perfect', 'Perfect (past tense)', lambda t: 'perfect' in t),
    ('pluperfect', 'Pluperfect', lambda t: 'pluperfect' in t),
    ('aorist', 'Aorist', lambda t: 'aorist' in t),
    ('imperfect', 'Imperfect', lambda t: 'imperfect' in t and 'past' in t),
    ('conditional-i', 'Conditional I', lambda t: 'conditional-i' in t),
    ('conditional-ii', 'Conditional II', lambda t: 'conditional-ii' in t),
    ('imperative', 'Imperative', lambda t: 'imperative' in t),
]
FUSED_FUTURE = re.compile(r'\S(ću|ćeš|će|ćemo|ćete|ćē)$')


def infer_person(form, tense, number):
    """Wiktionary's table loses the 1st/2nd person tags; recover them from Croatian endings/auxiliaries."""
    f = strip_accents(form).lower()
    toks = f.split()
    last = toks[-1] if toks else f
    sg = number == 'singular'
    if tense == 'future-i':
        for tok in toks[::-1]:
            for aux, p in (('ćemo', 1), ('ćete', 2), ('ćeš', 2), ('ću', 1)):
                if tok.endswith(aux):
                    return p
        return None
    if tense == 'future-ii':
        first = toks[0] if toks else ''
        if first.startswith('bud'):
            if first.endswith('mo') or (sg and first.endswith('m')):
                return 1
            if first.endswith('te') or (sg and first.endswith('š')):
                return 2
        return None
    if tense in ('perfect', 'pluperfect'):
        for tok in toks:
            if tok in ('sam', 'smo'):
                return 1
            if tok in ('si', 'ste'):
                return 2
        return None
    if tense in ('conditional-i', 'conditional-ii'):
        for tok in toks:
            if tok in ('bih', 'bismo'):
                return 1
            if tok in ('bi', 'biste'):
                return 2
        return None
    if tense == 'imperative':
        if sg:
            return 2
        if last.endswith('mo'):
            return 1
        if last.endswith('te'):
            return 2
        return None
    # present / aorist / imperfect
    if not sg:
        if last.endswith('mo'):
            return 1
        if last.endswith('te'):
            return 2
        return None
    if tense == 'present':
        if last.endswith('m'):
            return 1
        if last.endswith('š'):
            return 2
        return None
    if tense in ('aorist', 'imperfect'):
        return 1 if last.endswith('h') else 2
    return None


def conjugation_tables(forms):
    rows = [f for f in forms if not (set(f['tags']) & SKIP_TABLE_TAGS) and f['form'] not in ('',)]
    if not rows:
        return [], []
    nonfinite = collections.OrderedDict()
    participle = {('singular', g): [] for g in 'mfn'}
    participle.update({('plural', g): [] for g in 'mfn'})
    passive = {k: [] for k in participle}
    groups = collections.defaultdict(list)
    for f in rows:
        t = set(f['tags'])
        form = f['form']
        if 'infinitive' in t:
            nonfinite.setdefault('Infinitive', []).append(form)
            continue
        if 'noun-from-verb' in t:
            nonfinite.setdefault('Verbal noun', []).append(form)
            continue
        if 'error-unrecognized-form' in t:
            if 'third-person' in t:
                parts = form.rsplit(' ', 1)
                if len(parts) == 2 and parts[1] in 'mfn':
                    plain = strip_accents(parts[0]).lower()
                    # active (l-) participles end in -o / -la / -lo / -li / -le; anything else is passive
                    kind = participle if re.search(r'l[aoie]$', plain) or (parts[1] == 'm' and plain.endswith('o')) else passive
                    kind[('plural' if 'plural' in t else 'singular', parts[1])].append(parts[0])
                continue
            plain = strip_accents(form).lower()
            if plain.endswith(('vši', 'v')):
                nonfinite.setdefault('Past verbal adverb', []).append(form)
            elif plain.endswith('ći'):
                nonfinite.setdefault('Present verbal adverb', []).append(form)
            continue
        if 'participle' in t and 'passive' in t:
            nonfinite.setdefault('Passive participle', []).append(form)
            continue
        number = 'plural' if 'plural' in t else 'singular' if 'singular' in t else None
        if number is None:
            continue
        for key, title, test in TENSES:
            if test(t):
                groups[(key, number)].append(f)
                break

    tables = []
    for key, title, _ in TENSES:
        cells = {}
        for number in ('singular', 'plural'):
            fs = groups.get((key, number), [])
            if key == 'future-i':
                spaced = [f for f in fs if ' ' in f['form']]
                if spaced:
                    fs = [f for f in fs if not FUSED_FUTURE.search(f['form'])]
            for f in fs:
                p = 3 if 'third-person' in f['tags'] else infer_person(f['form'], key, number)
                if p is None:
                    continue
                cells.setdefault((p, number), []).append(f['form'])
        body = []
        for p, label in ((1, '1st'), (2, '2nd'), (3, '3rd')):
            sg = ' / '.join(x for x in uniq(cells.get((p, 'singular'), [])) if x != '-')
            pl = ' / '.join(x for x in uniq(cells.get((p, 'plural'), [])) if x != '-')
            if sg or pl:
                body.append([label, sg or '—', pl or '—'])
        if body:
            tables.append({'title': title, 'cols': ['', 'Singular', 'Plural'], 'rows': body})

    nf_rows = []
    for label in ('Infinitive', 'Present verbal adverb', 'Past verbal adverb', 'Verbal noun', 'Passive participle'):
        vals = [x for x in uniq(nonfinite.get(label, [])) if x != '-']
        if vals:
            nf_rows.append([label, ' / '.join(vals)])
    for name, table in (('Active past participle', participle), ('Passive participle', passive)):
        for number in ('singular', 'plural'):
            vals = [f"{' / '.join(uniq(table[(number, g)]))} ({g})" for g in 'mfn' if table[(number, g)]]
            if vals:
                nf_rows.append([f"{name} ({'sg.' if number == 'singular' else 'pl.'})", ', '.join(vals)])
    if nf_rows:
        tables.insert(0, {'title': 'Non-finite forms', 'cols': ['', ''], 'rows': nf_rows})

    index_forms = []
    for t in tables:
        for r in t['rows']:
            for cell in r[1:]:
                for v in cell.split(' / '):
                    v = re.sub(r' \([mfn]\)', '', v).strip()
                    for piece in v.split(', '):
                        piece = re.sub(r' \([mfn]\)$', '', piece).strip()
                        if piece and piece != '—' and ' ' not in piece:
                            index_forms.append(piece)
    return tables, index_forms


# ---------------------------------------------------------------- main extraction

def build(path, outdir):
    os.makedirs(outdir, exist_ok=True)
    stats = collections.Counter()
    entries = []
    formmap = []
    for line in open(path, encoding='utf-8'):
        d = json.loads(line)
        stats['raw'] += 1
        word = d.get('word', '').strip()
        if not word or d.get('lang_code') != 'sh' or is_cyrillic(word):
            continue
        stats['latin'] += 1
        pos = d.get('pos', '')
        senses = []
        formof_only = True
        for s in d.get('senses', []):
            tags = set(s.get('tags', []))
            if 'form_of' in s or 'form-of' in tags:
                for fo in s.get('form_of', []):
                    if fo.get('word') and not is_cyrillic(fo['word']):
                        formmap.append({'form': word, 'lemma': fo['word'], 'pos': pos,
                                        'tags': sorted(tags - {'form-of'}),
                                        'gloss': (s.get('glosses') or [''])[0][:120]})
                continue
            formof_only = False
            if tags & {'no-gloss', 'empty-gloss'} or not s.get('glosses'):
                continue
            if not keep_sense(tags):
                stats['dropped_sense_non_croatian'] += 1
                continue
            gloss = '; '.join(g.strip() for g in s['glosses'] if g.strip())
            # nested glosses repeat their parent text first; keep only the specific part
            if len(s['glosses']) > 1 and s['glosses'][-1].strip():
                gloss = s['glosses'][-1].strip()
            exs = []
            for e in s.get('examples', []):
                text = (e.get('text') or '').strip()
                if not text or is_cyrillic(text) or len(text) > 320:
                    continue
                core = text.replace('[…]', '').strip()
                if any(x['hr'].startswith(core) or core.startswith(x['hr']) for x in exs):
                    continue
                exs.append({'hr': text, 'en': (e.get('translation') or e.get('english') or '').strip(),
                            'ref': (e.get('ref') or '')[:120], 'src': 'wikt'})
                if len(exs) >= 3:
                    break
            sense = {'g': gloss, 'l': sense_labels(s),
                     'dialect': sorted(tags & DIALECT_TAGS)}
            if exs:
                sense['ex'] = exs
            alt = latin([a.get('word', '') for a in s.get('alt_of', [])])
            if alt:
                sense['see'] = alt
            syn = word_list(s.get('synonyms'))
            ant = word_list(s.get('antonyms'))
            if syn:
                sense['syn'] = syn
            if ant:
                sense['ant'] = ant
            senses.append(sense)
        if not senses:
            stats['formof_only' if formof_only else 'dropped_entry_non_croatian'] += 1
            continue

        forms = d.get('forms', [])
        canonical = next((f['form'] for f in forms if 'canonical' in f.get('tags', [])), word)
        ctags = set(next((f.get('tags', []) for f in forms if 'canonical' in f.get('tags', [])), []))
        gram = []
        for g in GENDERS:
            if g in ctags:
                gram.append(GENDER_SHORT[g])
        if 'animate' in ctags:
            gram.append('anim')
        aspect = next((a for a in ('imperfective', 'perfective', 'biaspectual') if a in ctags), None)
        if not aspect:
            for h in d.get('head_templates', []):
                a = h.get('args', {}).get('2')
                if h.get('name') == 'sh-verb' and a in ('impf', 'pf', 'biasp'):
                    aspect = {'impf': 'imperfective', 'pf': 'perfective', 'biasp': 'biaspectual'}[a]
        if aspect:
            gram.append({'imperfective': 'impf', 'perfective': 'pf', 'biaspectual': 'impf/pf'}[aspect])
        if pos == 'noun' and not gram:
            for h in d.get('head_templates', []):
                a = h.get('args', {}).get('2', '')
                if h.get('name') == 'sh-noun' and a:
                    gram.append(a.replace('-an', ' anim').replace('-in', '').replace('-pr', ''))

        related = collections.OrderedDict()
        alternatives = []
        for f in forms:
            t = set(f.get('tags', []))
            if f.get('source') or 'canonical' in t or 'Cyrillic' in t or is_cyrillic(f.get('form', '')):
                continue
            form = f.get('form', '').strip()
            if not form:
                continue
            if 'alternative' in t:
                label = ', '.join(x for x in sorted(t - {'alternative'}))
                alternatives.append({'form': form, 'label': label})
                continue
            for tag, name in (('diminutive', 'Diminutive'), ('augmentative', 'Augmentative'),
                              ('relational', 'Relational adjective'), ('comparative', 'Comparative'),
                              ('definite', 'Definite form'), ('noun-from-verb', 'Verbal noun')):
                if tag in t:
                    related.setdefault(name, []).append(form)
                    break
            else:
                if pos == 'verb' and 'perfective' in t:
                    related.setdefault('Perfective', []).append(form)
                elif pos == 'verb' and 'imperfective' in t:
                    related.setdefault('Imperfective', []).append(form)
                elif pos == 'noun' and 'feminine' in t:
                    related.setdefault('Feminine', []).append(form)
                elif pos == 'noun' and 'masculine' in t:
                    related.setdefault('Masculine', []).append(form)

        infl = [{'form': f['form'], 'tags': f.get('tags', [])} for f in forms
                if f.get('source') in ('declension', 'conjugation') and not is_cyrillic(f.get('form', ''))]
        index_forms = []
        if pos == 'verb' and any(f2.get('source') == 'conjugation' for f2 in forms):
            tables, index_forms = conjugation_tables(infl)
        else:
            tables = declension_tables(infl)
            for t in tables:
                for r in t['rows']:
                    for cell in r[1:]:
                        index_forms.extend(v.strip() for v in cell.split(' / ') if v.strip())
        index_forms = uniq(strip_accents(x) for x in index_forms if x and x != '—')

        ipa = ''
        for snd in d.get('sounds', []):
            if 'ipa' in snd and not set(snd.get('tags', [])) & {'Serbia', 'Ekavian'}:
                ipa = snd['ipa']
                break
        hyph = ''
        if d.get('hyphenations'):
            hyph = '-'.join(d['hyphenations'][0].get('parts', []))

        dialect_sets = [set(s['dialect']) for s in senses]
        if all('Kajkavian' in ds for ds in dialect_sets):
            dialect = 'kaj'
        elif all('Chakavian' in ds for ds in dialect_sets):
            dialect = 'cak'
        elif all(ds & DIALECT_TAGS for ds in dialect_sets):
            dialect = 'kaj' if any('Kajkavian' in ds for ds in dialect_sets) else 'cak'
        else:
            dialect = 'std'

        entry = {
            'word': word,
            'acc': canonical if strip_accents(canonical) == word or strip_accents(canonical).lower() == word.lower() else word,
            'pos': pos,
            'gram': ' '.join(gram),
            'dialect': dialect,
            'ipa': ipa,
            'hyph': hyph,
            'senses': senses,
            'tables': tables,
            'iforms': index_forms,
            'alt': alternatives,
            'rel': related,
            'syn': word_list(d.get('synonyms')),
            'ant': word_list(d.get('antonyms')),
            'derived': word_list(d.get('derived')),
            'related': word_list(d.get('related')),
            'ety': (d.get('etymology_text') or '')[:700],
        }
        entries.append(entry)
        stats['entries'] += 1
        stats['dialect_' + dialect] += 1
        stats['pos_' + pos] += 1
        if any(s.get('ex') for s in senses):
            stats['with_wikt_examples'] += 1
        if tables:
            stats['with_tables'] += 1

    # stable ids: sort by word then pos for reproducibility
    entries.sort(key=lambda e: (strip_accents(e['word']).lower(), e['word'], e['pos']))
    for i, e in enumerate(entries, 1):
        e['id'] = i
        e['prio'] = priority(e)
    with open(os.path.join(outdir, 'entries.jsonl'), 'w', encoding='utf-8') as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + '\n')
    with open(os.path.join(outdir, 'formmap.jsonl'), 'w', encoding='utf-8') as fh:
        for m in formmap:
            fh.write(json.dumps(m, ensure_ascii=False) + '\n')
    stats['formmap'] = len(formmap)
    with open(os.path.join(outdir, 'stats.json'), 'w', encoding='utf-8') as fh:
        json.dump(dict(stats), fh, indent=1, ensure_ascii=False)
    print(json.dumps(dict(stats), indent=1, ensure_ascii=False))


RAREISH = re.compile(r'\b(archaic|obsolete|dated|rare|historical|regional|dialectal)\b')


def priority(e):
    """Rough commonness score used only to order AI enrichment work (higher = more common)."""
    s = 0.0
    s += min(len(e['senses']), 6)
    s += 3 if any(x.get('ex') for x in e['senses']) else 0
    s += 2 if e['tables'] else 0
    s += 1 if e['ipa'] else 0
    s += 1 if e['rel'] else 0
    s += 1 if len(e['word']) <= 7 else 0
    s -= 4 if e['pos'] in ('name', 'suffix', 'prefix', 'character', 'interfix', 'infix', 'symbol', 'combining_form') else 0
    if all(RAREISH.search(x.get('l', '')) for x in e['senses']):
        s -= 3
    if e['word'][:1].isupper() and e['pos'] != 'name':
        s -= 1
    return round(s, 1)


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
