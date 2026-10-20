"""Split entries into enrichment batches for the AI example/Kajkavian pass.

Usage: python -I tools/make_batches.py data/work/entries.jsonl data/enrich [batch_size]
Writes data/enrich/batches/bNNNN.txt and data/enrich/manifest.json (batch ids, most common words first).
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

SKIP_POS = {'suffix', 'prefix', 'character', 'interfix', 'infix', 'symbol', 'combining_form'}


def line_for(e):
    senses = []
    for i, s in enumerate(e['senses'][:5], 1):
        g = s['g'].replace('\t', ' ').replace('\n', ' ')
        if len(g) > 110:
            g = g[:107] + '...'
        lab = f" [{s['l']}]" if s.get('l') else ''
        senses.append(f'{i}. {g}{lab}')
    extra = []
    n_ex = sum(1 for s in e['senses'] for x in s.get('ex', []) if x.get('en'))
    if n_ex:
        extra.append(f'wikt_examples={n_ex}')
    kaj_alt = [a['form'] for a in e.get('alt', []) if 'Kajkavian' in a.get('label', '')]
    if kaj_alt:
        extra.append('wikt_kajkavian=' + ', '.join(kaj_alt))
    syn = [w for s in e['senses'] for w in s.get('syn', [])][:4]
    if e['dialect'] != 'std' and syn:
        extra.append('synonyms=' + ', '.join(syn))
    pos = e['pos'] + (f" {e['gram']}" if e['gram'] else '')
    dialect = {'std': 'STD', 'kaj': 'KAJKAVIAN', 'cak': 'CHAKAVIAN'}[e['dialect']]
    return '\t'.join([str(e['id']), e['acc'], pos, dialect, ' '.join(senses), '; '.join(extra)])


def main(src, outdir, size=120):
    entries = [json.loads(l) for l in open(src, encoding='utf-8')]
    todo = [e for e in entries if e['pos'] not in SKIP_POS]
    todo.sort(key=lambda e: (-e['prio'], e['id']))
    os.makedirs(os.path.join(outdir, 'batches'), exist_ok=True)
    os.makedirs(os.path.join(outdir, 'out'), exist_ok=True)
    os.makedirs(os.path.join(outdir, 'review'), exist_ok=True)
    batches = []
    for i in range(0, len(todo), size):
        chunk = todo[i:i + size]
        bid = f'b{len(batches) + 1:04d}'
        with open(os.path.join(outdir, 'batches', bid + '.txt'), 'w', encoding='utf-8') as fh:
            fh.write('id\theadword\tpos\tdialect\tsenses\textra\n')
            for e in chunk:
                fh.write(line_for(e) + '\n')
        batches.append({'id': bid, 'n': len(chunk), 'first': chunk[0]['id'], 'names': sum(e['pos'] == 'name' for e in chunk)})
    with open(os.path.join(outdir, 'manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump({'batch_size': size, 'entries': len(todo), 'batches': batches}, fh, indent=1)
    print(len(todo), 'entries in', len(batches), 'batches')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 120)
