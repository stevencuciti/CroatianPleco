"""Heuristic QA over the AI enrichment (generated + reviewed). Flags entries for a targeted fix pass.

Usage: python -I tools/qa_enrichment.py data/work data/enrich [out_dir]
Writes <out_dir>/flags.jsonl (one line per flagged entry with reasons) and prints a summary.
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hrtext import fold, strip_accents  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')

# Serbian / Bosnian vocabulary or ekavian spellings that should not appear in standard Croatian examples.
SERBIAN = {'hleb', 'hljeb', 'voz', 'vozom', 'pozorište', 'pozorišta', 'hiljada', 'hiljadu', 'hiljade', 'šta',
           'univerzitet', 'univerziteta', 'fudbal', 'opština', 'opštine', 'sedmica', 'kafa', 'kafu', 'kafe',
           'čas', 'pantalone', 'paradajz', 'pasulj', 'spanać', 'sto', 'stolica', 'uopšte', 'vazduh', 'vazduha',
           'tačka', 'tačno', 'apoteka', 'hemija', 'istorija', 'muzika', 'muzike', 'avion', 'avionom',
           'mleko', 'dete', 'deca', 'dece', 'lepo', 'lep', 'lepa', 'reka', 'reke', 'vreme', 'vremena', 'devojka',
           'devojke', 'mesto', 'mesta', 'svet', 'sveta', 'pesma', 'pesme', 'leto', 'leta', 'cena', 'cene',
           'beo', 'bela', 'belo', 'hteo', 'htela', 'nedelja', 'nedelje', 'kijavica', 'ćebe', 'pegla', 'pirinač'}
# 'sto' (= stol) and 'stolica' etc. are ambiguous; keep a separate allow-list check below.
AMBIGUOUS = {'sto', 'stolica', 'čas', 'svet', 'sveta', 'leta', 'leto', 'mesta', 'cene', 'cena', 'kafe', 'vremena',
             'muzika', 'muzike', 'avion', 'avionom', 'nedelja', 'nedelje', 'lep', 'deca'}

# Shtokavian words that a Kajkavian sentence normally replaces.
SHTOKAVIAN = {'što', 'šta', 'ništa', 'nešto', 'sutra', 'jučer', 'gdje', 'ovdje', 'čovjek', 'djeca', 'dijete',
              'mlijeko', 'lijepo', 'lijep', 'lijepa', 'rijeka', 'vrijeme', 'bijel', 'bijela', 'bijelo', 'mjesto',
              'svijet', 'pjesma', 'ljeto', 'cijena', 'ići', 'vidjeti', 'htio', 'htjela', 'želio', 'čekati', 'čekam',
              'vjerovati', 'nisam', 'nismo', 'nisu', 'ću', 'ćeš', 'ćemo', 'ćete', 'jesam', 'neću', 'hoću', 'tko'}
KAJ_OK = set()


def load(enrich_dir):
    objs = {}
    for sub in ('out', 'review', 'fix'):
        for p in sorted(glob.glob(os.path.join(enrich_dir, sub, '[bf]*.jsonl'))):
            for line in open(p, encoding='utf-8'):
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    objs[int(o['id'])] = o
                except (ValueError, KeyError, TypeError):
                    pass
    return objs


def words(s):
    return re.findall(r"[a-zA-ZčćšžđČĆŠŽĐ]+", strip_accents(s).lower())


def stem_ok(entry, sentence):
    """Does the sentence contain the headword (any inflected form, or a word sharing its stem)?"""
    toks = {fold(t) for t in words(sentence)}
    head = fold(entry['word'])
    forms = {fold(x) for x in entry.get('iforms', [])} | {head}
    for part in head.split():
        forms.add(part)
    if toks & forms:
        return True
    base = head.split()[0] if head else ''
    # strip common infinitive / case endings for a loose stem
    stem = re.sub(r'(ti|ći|iti|ati|eti|uti|ovati|ivati|nuti|a|e|i|o|u|ost|ski|ni|an|en)$', '', base)
    stem = stem[:max(3, min(len(stem), 5))]
    if len(stem) >= 3 and any(t.startswith(stem) for t in toks):
        return True
    # reflexive / multiword headwords: accept when every content part occurs
    return False


def main(work_dir, enrich_dir, out_dir):
    entries = {}
    for l in open(os.path.join(work_dir, 'entries.jsonl'), encoding='utf-8'):
        e = json.loads(l)
        entries[e['id']] = e
    objs = load(enrich_dir)
    stats = collections.Counter()
    flags = []
    for eid, o in objs.items():
        e = entries.get(eid)
        if not e:
            stats['unknown_id'] += 1
            continue
        reasons = []
        exs = o.get('ex') or []
        if not isinstance(exs, list) or not exs:
            reasons.append('no examples')
        for x in exs if isinstance(exs, list) else []:
            if not (isinstance(x, list) and len(x) >= 2 and x[0] and x[1]):
                reasons.append('malformed example')
                continue
            ws = set(words(x[0]))
            if e['dialect'] == 'std':
                bad = sorted((ws & SERBIAN) - AMBIGUOUS)
                if bad and fold(e['word']) not in {fold(b) for b in bad}:
                    reasons.append('non-Croatian vocabulary: ' + ', '.join(bad))
            if not stem_ok(e, x[0]) and e['pos'] not in ('name',):
                reasons.append('headword missing in: ' + x[0][:80])
            if re.search(r'[̀-ͯȀ-ȗ]', x[0]) or re.search('[ȁȃȅȇȉȋȍȏȑȓȕȗ]', x[0]):
                reasons.append('accent marks in example')
        k = o.get('k')
        if isinstance(k, dict) and k.get('ex'):
            kex = k['ex']
            if isinstance(kex, list) and len(kex) >= 2 and isinstance(kex[0], str):
                ws = set(words(kex[0]))
                shto = sorted((ws & SHTOKAVIAN) - KAJ_OK)
                # the headword itself (or its standard form) may legitimately be Shtokavian-looking
                shto = [w for w in shto if fold(w) != fold(e['word']) and fold(w) not in {fold(x) for x in re.split(r'[,; ]+', k.get('w', ''))}]
                if len(shto) >= 1:
                    reasons.append('Shtokavian words in Kajkavian sentence: ' + ', '.join(shto))
                kws = [fold(w).split()[0] for w in re.split(r'[,;/]', k.get('w', '')) if fold(w)]
                toks = {fold(t) for t in words(kex[0])}
                suppletive = fold(e['word']) in ('biti', 'iti', 'ici', 'jesti', 'dati', 'imati', 'htjeti', 'moci', 'ja', 'ti', 'on', 'mi', 'vi', 'oni', 'ona', 'ono', 'se')
                if kws and not suppletive and not any(len(kw) <= 3 or any(t.startswith(kw[:3]) for t in toks) for kw in kws):
                    reasons.append('Kajkavian word missing in Kajkavian sentence')
            else:
                reasons.append('malformed Kajkavian example')
        if isinstance(k, dict) and re.search('[üöə]', k.get('w', '') + json.dumps(k.get('ex', ''), ensure_ascii=False)):
            reasons.append('special letters in Kajkavian')
        if reasons:
            flags.append({'id': eid, 'word': e['word'], 'pos': e['pos'], 'reasons': sorted(set(reasons))})
            for r in set(x.split(':')[0] for x in reasons):
                stats[r] += 1
    stats['checked'] = len(objs)
    stats['flagged'] = len(flags)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'flags.jsonl'), 'w', encoding='utf-8') as fh:
        for f in sorted(flags, key=lambda x: x['id']):
            fh.write(json.dumps(f, ensure_ascii=False) + '\n')
    print(json.dumps(dict(stats), indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else os.path.join(sys.argv[2], 'qa'))
