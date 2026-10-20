import json, sys, collections
import sys; sys.stdout.reconfigure(encoding="utf-8")
path = sys.argv[1]
n = 0; pos = collections.Counter(); keys = collections.Counter(); tags = collections.Counter()
latin = 0; cyr = 0; formof = 0; withex = 0; kaj = 0; kaj_words = []
sense_tags = collections.Counter(); cats = collections.Counter()
sample = {}
for line in open(path, encoding='utf-8'):
    d = json.loads(line); n += 1
    w = d.get('word', '')
    pos[d.get('pos')] += 1
    for k in d: keys[k] += 1
    if any('Ѐ' <= ch <= 'ӿ' for ch in w): cyr += 1
    else: latin += 1
    senses = d.get('senses', [])
    if senses and all(('form_of' in s or 'alt_of' in s) for s in senses): formof += 1
    if any(s.get('examples') for s in senses): withex += 1
    blob = json.dumps(d, ensure_ascii=False)
    if 'Kajkavian' in blob:
        kaj += 1
        if len(kaj_words) < 40: kaj_words.append(w)
    for s in senses:
        for t in s.get('tags', []): sense_tags[t] += 1
        for t in s.get('raw_tags', []): sense_tags['raw:'+t] += 1
    for c in d.get('categories', []):
        cats[c if isinstance(c, str) else c.get('name')] += 1
    if w in ('kuća', 'hiža', 'kaj', 'pas', 'ići') and w not in sample: sample[w] = d
print('entries', n, 'latin', latin, 'cyr', cyr, 'formof-only', formof, 'with examples', withex, 'mention Kajkavian', kaj)
print('pos', pos.most_common(30))
print('keys', keys.most_common(40))
print('sense tags', sense_tags.most_common(80))
print('kaj sample', kaj_words)
print('cats', [c for c in cats.most_common(400) if c[0] and ('Kajkav' in c[0] or 'Croatian' in c[0] or 'Serbian' in c[0])][:40])
for w, d in sample.items():
    print('=====', w); print(json.dumps(d, ensure_ascii=False)[:3500])
