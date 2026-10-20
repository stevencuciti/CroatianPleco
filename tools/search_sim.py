"""Python port of DictionaryDb.search (app/src/hr/rjecnik/data/DictionaryDb.java) for testing ranking offline.

Usage: python -I tools/search_sim.py build/db/dict.db "query" [mode: 0 auto, 1 hr, 2 en] [n]
       python -I tools/search_sim.py build/db/dict.db --suite
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hrtext import fold, en_norm, strip_accents  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')
HRL = set('čćšžđČĆŠŽĐ')


def search(db, query, mode=0, limit=80):
    q = query.strip()
    if not q:
        return []
    qf, qe = fold(q), en_norm(q)
    hits = {}

    def offer(eid, score, typ, form=None, info=None):
        h = hits.get(eid)
        if h is None or score > h[0]:
            hits[eid] = (score, typ, form, info)

    if mode in (0, 1) and qf:
        for eid, kind, form, info in db.execute('SELECT entry_id, kind, form, info FROM hr_index WHERE term = ? LIMIT 300', (qf,)):
            score = {0: 1000, 1: 920, 2: 860}.get(kind, 820)
            typ = {0: 'HEAD', 1: 'KAJ', 2: 'FORM'}.get(kind, 'ALT')
            offer(eid, score, typ, None if kind == 0 else form, None if kind == 0 else info)
        for eid, kind, term, form in db.execute('SELECT entry_id, kind, term, form FROM hr_index WHERE term > ? AND term < ? '
                                                'AND kind IN (0,1) ORDER BY term LIMIT 400', (qf, qf + '￿')):
            score = max(300, 600 - 4 * (len(term) - len(qf)))
            offer(eid, score, 'KAJ' if kind == 1 else 'HR_PREFIX', form if kind == 1 else None)
    if mode in (0, 2) and qe:
        pen = 400 if mode == 0 and any(c in HRL for c in q) else 0
        for eid, w in db.execute('SELECT entry_id, weight FROM en_index WHERE term = ? ORDER BY weight DESC LIMIT 400', (qe,)):
            offer(eid, 300 + int(w * 0.7) - pen, 'EN')
        if len(qe) >= 2:
            for eid, w in db.execute('SELECT entry_id, weight FROM en_index WHERE term > ? AND term < ? ORDER BY weight DESC LIMIT 300',
                                     (qe, qe + '￿')):
                offer(eid, 200 + int(w * 0.35) - pen, 'EN_PREFIX')
    out = []
    for eid, (score, typ, form, info) in hits.items():
        r = db.execute('SELECT headword, pos, dialect, freq, gloss, kaj FROM entries WHERE id = ?', (eid,)).fetchone()
        if not r:
            continue
        hw, pos, dialect, freq, gloss, kaj = r
        s = score + (freq or 2) * 12
        if pos == 'name':
            s -= 60
        if typ == 'HEAD' and any(c in HRL for c in q) and strip_accents(q).lower() == hw.lower():
            s += 40
        if dialect in ('kaj', 'cak') and typ not in ('HEAD', 'KAJ', 'HR_PREFIX'):
            s -= 20
        out.append((s, freq or 2, hw, pos, dialect, typ, form, info, gloss, kaj))
    out.sort(key=lambda x: (-x[0], -x[1], len(x[2])))
    return out[:limit]


SUITE = ['house', 'kuća', 'kuca', 'dog', 'psa', 'pes', 'go', 'to go', 'be', 'red', 'black', 'hiža', 'kaj', 'what',
         'water', 'voda', 'beautiful', 'lijep', 'dober', 'yesterday', 'jučer', 'fčera', 'thank you', 'hvala',
         'čovjek', 'človek', 'cov', 'dje', 'đak', 'dak', 'idem', 'išao', 'bolji', 'love', 'volim', 'bread', 'kruh',
         'mother', 'father', 'mushroom', 'hungry', 'lačen', 'which', 'šteri', 'Zagreb', 'Čakovec', 'run', 'eat']


if __name__ == '__main__':
    db = sqlite3.connect(sys.argv[1])
    if sys.argv[2] == '--suite':
        for q in SUITE:
            res = search(db, q, 0, 5)
            print(f'\n### {q}')
            for r in res:
                extra = f' [{r[6]} — {r[7]}]' if r[6] else ''
                kaj = f'  | kaj: {r[9]}' if r[9] else ''
                print(f'  {r[0]:5d} f{r[1]} {r[2]} ({r[3]}{"," + r[4] if r[4] != "std" else ""}) {r[5]}{extra}: {r[8][:70]}{kaj}')
    else:
        mode = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 15
        for r in search(db, sys.argv[2], mode, n):
            print(r)
