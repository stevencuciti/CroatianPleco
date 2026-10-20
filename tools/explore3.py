import json, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
path = sys.argv[1]
vt = collections.Counter(); nt = collections.Counter(); at = collections.Counter(); headargs = collections.Counter(); canon = collections.Counter()
ex = {}
for line in open(path, encoding='utf-8'):
    d = json.loads(line); w = d['word']
    if any('Ѐ' <= ch <= 'ӿ' for ch in w): continue
    p = d['pos']
    for f in d.get('forms', []):
        t = tuple(sorted(f.get('tags', [])))
        if 'canonical' in t: canon[(p,)+t] += 1; continue
        src = f.get('source')
        key = (src,) + t
        if p == 'verb': vt[key] += 1
        elif p == 'noun': nt[key] += 1
        elif p == 'adj': at[key] += 1
        if p == 'verb' and key not in ex: ex[key] = (w, f['form'])
    for h in d.get('head_templates', []):
        if h['name'] in ('sh-verb', 'sh-noun', 'sh-adj', 'sh-adv'):
            for k in h.get('args', {}): headargs[(h['name'], k)] += 1
print('VERB'); [print(c, k, ex.get(k)) for k, c in vt.most_common(120)]
print('NOUN'); [print(c, k) for k, c in nt.most_common(50)]
print('ADJ'); [print(c, k) for k, c in at.most_common(40)]
print('HEADARGS', headargs.most_common(60))
print('CANON', canon.most_common(40))
