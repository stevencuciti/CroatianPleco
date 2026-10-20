"""Turn QA flags into fix batches: data/enrich/fix_in/fNNN.txt (input row + current object + reasons).

Usage: python -I tools/make_fix_batches.py data/enrich [batch_size]
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')


def main(enrich_dir, size=60):
    rows = {}
    for p in glob.glob(os.path.join(enrich_dir, 'batches', 'b*.txt')):
        for line in open(p, encoding='utf-8').read().splitlines()[1:]:
            rows[int(line.split('\t', 1)[0])] = line
    current = {}
    for sub in ('out', 'review'):
        for p in sorted(glob.glob(os.path.join(enrich_dir, sub, 'b*.jsonl'))):
            for line in open(p, encoding='utf-8'):
                try:
                    o = json.loads(line)
                    current[int(o['id'])] = o
                except (ValueError, KeyError, TypeError):
                    pass
    flags = [json.loads(l) for l in open(os.path.join(enrich_dir, 'qa', 'flags.jsonl'), encoding='utf-8')]
    out_dir = os.path.join(enrich_dir, 'fix_in')
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(enrich_dir, 'fix'), exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, 'f*.txt')):
        os.remove(old)
    ids = []
    for i in range(0, len(flags), size):
        fid = f'f{i // size + 1:03d}'
        with open(os.path.join(out_dir, fid + '.txt'), 'w', encoding='utf-8') as fh:
            for f in flags[i:i + size]:
                fh.write('ENTRY ' + rows.get(f['id'], str(f['id'])) + '\n')
                fh.write('CURRENT ' + json.dumps(current.get(f['id'], {'id': f['id']}), ensure_ascii=False) + '\n')
                fh.write('FLAGS ' + ' | '.join(f['reasons']) + '\n\n')
        ids.append(fid)
    print(json.dumps(ids))


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 60)
