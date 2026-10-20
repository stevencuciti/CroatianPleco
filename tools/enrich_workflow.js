export const meta = {
  name: 'enrich-dictionary',
  description: 'Generate Croatian + Međimurje Kajkavian examples for dictionary batches, then review each batch',
  phases: [
    { title: 'Generate', detail: 'one agent per batch writes examples + Kajkavian forms' },
    { title: 'Review', detail: 'strict reviewer corrects each batch' },
  ],
}

const BASE = args.base
const toBatch = (x) => (typeof x === 'string'
  ? { id: x, in: 'batches\\' + x + '.txt', out: 'out\\' + x + '.jsonl', rev: 'review\\' + x + '.jsonl' } : x)
let ids = args.batches || []
if (args.total) {
  ids = []
  for (let i = args.offset; i <= args.total; i += args.stride) ids.push('b' + String(i).padStart(4, '0'))
}
const batches = ids.map(toBatch)
log(`${batches.length} batches: ${batches.length ? batches[0].id : ''} … ${batches.length ? batches[batches.length - 1].id : ''}`)

const GEN_SCHEMA = {
  type: 'object',
  properties: { batch: { type: 'string' }, written: { type: 'integer' }, notes: { type: 'string' } },
  required: ['batch', 'written'],
}
const REV_SCHEMA = {
  type: 'object',
  properties: {
    batch: { type: 'string' }, checked: { type: 'integer' }, changed: { type: 'integer' },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['batch', 'checked', 'changed'],
}

const genPrompt = (b) => `You are an expert lexicographer for an offline Croatian–English learner's dictionary app (Pleco-style). You have native-level command of standard Croatian (ijekavian, current Croatian norm) and of the Međimurje Kajkavian dialect (Čakovec / Prelog / Mursko Središće area).

INPUT: read the TSV file ${BASE}\\${b.in} (header row, then one dictionary entry per row taken from Wiktionary: id, headword with Wiktionary tonal accent marks, part of speech + gender/aspect, dialect of the entry (STD = standard Croatian, KAJKAVIAN, CHAKAVIAN), numbered English senses with [labels], extra hints).

For EVERY row produce one JSON object with these keys:
- "id": the row id (integer).
- "f": commonness of the word in present-day Croatian, 1–5 (5 = among the ~1,000 words used daily; 4 = common, top ~5,000; 3 = known to every adult, top ~15,000; 2 = uncommon or specialised; 1 = rare, archaic, technical or regional). For KAJKAVIAN/CHAKAVIAN entries rate commonness within that dialect.
- "ex": example sentences with natural English translations, as [["Croatian sentence", "English translation"], ...].
  * Count: f=5 → 3 examples; f=3 or 4 → 2; f≤2 and proper names → 1. If extra shows wikt_examples≥2, give one fewer (minimum 1).
  * Cover the most important senses, sense 1 first. Every example must really contain the headword (any inflected form) used in that sense.
  * Short and natural (4–14 words), modern everyday usage, correct case/agreement/aspect, clitics in second position, ijekavian spelling, Croatian (not Serbian/Bosnian) vocabulary: kruh not hleb, vlak not voz, kazalište not pozorište, tisuća not hiljada, tjedan not nedelja, što not šta, ću + infinitive (radit ću) not fused radiću.
  * Use normal orthography with č ć đ š ž and NEVER the Wiktionary tonal accent marks.
  * Prefer the Croatian norm in examples: pokraj/kraj (not pored), srčana greška (not srčana mana), glazba (not muzika), obitelj, zrakoplov, sveučilište, kolodvor, točka, opći, lijek etc.
  * For KAJKAVIAN entries the "ex" sentences are in Kajkavian (Međimurje style where possible); for CHAKAVIAN entries in Chakavian. For those entries also add "std": the standard Croatian equivalent word(s) as a string.
- "k": the Međimurje Kajkavian equivalent, an object {"w": ..., "ex": [...], "n": ..., "c": ...}:
  * "w": the Međimurje word(s), comma-separated if several are common. Plain Croatian orthography only (no accent marks, no IPA, no special letters such as ü ö ə). If Međimurje simply uses the standard word, give it in its Kajkavian shape (e.g. dober for dobar, človek for čovjek, pes for pas) or unchanged if identical. If extra shows wikt_kajkavian, check it and prefer it when it is right for Međimurje.
  * "ex": ["Kajkavian sentence", "English translation"] — ONE short sentence in Međimurje Kajkavian using Kajkavian grammar consistently (kaj, nej / ne, bom/boš/bo + l-participle for the future, sem/si/je + l-participle for the past, vu / v, z, genitive plural in -of/-ov etc.). Only when f ≥ 3; omit otherwise.
  * Never invent a Kajkavian form by mechanical sound changes. Kajkavian sentences must use Kajkavian vocabulary and morphology throughout (čakati not čekati, verovati, delati, gda, zutra, nekaj/nikaj, ne/nej, kre, vu), not just the headword. If unsure, give the standard word and "c": "l".
  * "n": optional note of at most 12 words (e.g. regional variation, "Zagorje: …", "loanword, same as standard"). Omit when nothing useful.
  * "c": your honest confidence that "w" is genuine Međimurje usage: "h" high, "m" medium, "l" low (guessed by analogy). Technical, scientific and modern loanwords are normally the same as standard — mark them "h" when they are simply identical.
  * For KAJKAVIAN entries "k" is optional: include it only if the Međimurje form differs from the headword or you have a useful note.
  * Omit "k" for proper names unless the local Kajkavian name differs (e.g. Međimurje → Medžimurje), and for words where you genuinely cannot say.
OUTPUT: write all objects as JSONL (one compact JSON object per line, UTF-8, valid JSON, double quotes, no comments), in input order, to ${BASE}\\${b.out} using the Write tool. Every input id must appear exactly once. Do not write any other files.
Return {"batch": "${b.id}", "written": <number of lines written>, "notes": "<anything notable, at most 40 words>"}.`

const revPrompt = (b) => `You are a strict senior reviewer for a Croatian–English–Kajkavian dictionary app: a native speaker of standard Croatian (ijekavian, current Croatian norm) who also grew up speaking Međimurje Kajkavian (Čakovec / Prelog area).

Read the input entries ${BASE}\\${b.in} (TSV from Wiktionary: id, headword, pos, dialect, English senses, extra) and the generated enrichment ${BASE}\\${b.out} (JSONL, one object per entry with keys id, f, ex, std, k = {w, ex, n, c}).

Check EVERY generated object against its input row:
1. Croatian examples: grammatical (case, agreement, aspect, clitic position), natural, standard ijekavian Croatian norm (no Serbian/Bosnian lexicon or ekavian forms), no Wiktionary accent marks, each actually contains the headword (any inflected form) in the sense it illustrates, sense 1 covered first.
2. English translations faithful and natural.
3. "f" plausible (5 = everyday top-1,000 word … 1 = rare/archaic/technical).
4. Kajkavian: "w" plausible for Međimurje (not Shtokavian forms such as što/šta, ništa→nikaj, sutra→zutra, etc. where Kajkavian differs), the "ex" sentence uses Kajkavian grammar consistently and contains "w", "c" is honest — lower it when doubtful, and replace a clearly wrong Kajkavian form with a better one or delete the whole "k" key rather than leave an error.
5. Valid JSON, all ids present, schema respected.

Write the CORRECTED full replacement objects (same schema, complete object, not a diff) ONLY for entries that need any change, as JSONL to ${BASE}\\${b.rev} using the Write tool. If an id is missing from the generated file, write a complete object for it. If nothing needs changing, write an empty file. Do not modify any other files.
Return {"batch": "${b.id}", "checked": <entries checked>, "changed": <objects written>, "issues": [<up to 10 short descriptions of the most important problems you fixed>]}.`

const results = await pipeline(
  batches,
  (b) => agent(genPrompt(b), { label: `gen:${b.id}`, phase: 'Generate', schema: GEN_SCHEMA, effort: args.genEffort || 'medium' }),
  (g, b) => args.noReview ? Promise.resolve({ gen: g, rev: null }) : agent(revPrompt(b), { label: `review:${b.id}`, phase: 'Review', schema: REV_SCHEMA, effort: args.revEffort || 'medium' })
    .then((r) => ({ gen: g, rev: r })),
)
return results
