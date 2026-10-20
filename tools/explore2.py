import json, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
path = sys.argv[1]
audio = 0; audio_words = []; ipa = 0; mp3 = 0; ogg = 0
want = {'raditi','dobar','napraviti','biti','lijep','ja','u','i','mlijeko','mleko','hiža','fčera','človek','Zagreb','brzo','kruh','hleb'}
shown = set(); lab = collections.Counter()
for line in open(path, encoding='utf-8'):
    d = json.loads(line); w = d['word']
    for s in d.get('sounds', []):
        if 'ipa' in s: ipa += 1
        if 'audio' in s:
            audio += 1
            if 'mp3_url' in s: mp3 += 1
            if 'ogg_url' in s: ogg += 1
            if len(audio_words) < 15: audio_words.append((w, s.get('audio'), s.get('tags'), s.get('mp3_url','')[:90]))
    for s in d.get('senses', []):
        for g in s.get('raw_glosses', []):
            if g.startswith('('):
                lab[g[1:g.find(')')]] += 1
    if w in want and (w, d['pos']) not in shown:
        shown.add((w, d['pos']))
        d2 = dict(d); d2.pop('etymology_templates', None); d2.pop('head_templates', None)
        print('=====', w, d['pos']); print(json.dumps(d2, ensure_ascii=False)[:2500])
print('ipa', ipa, 'audio', audio, 'mp3', mp3, 'ogg', ogg)
print(audio_words)
print(lab.most_common(60))
