#!/usr/bin/env python3
"""
Capio International — Account Intelligence: the canonical derivation.

This file is the statement of record for how the dashboard turns its two Google
Sheets into the boards it draws. `buildData()` inside index.html is a direct port
of it; run this and compare its report against the page — they must agree.

    python3 build_data.py                derive both boards and report
    python3 build_data.py --board netnew  just one of them
    python3 build_data.py --embed        also bake the result into index.html
    python3 build_data.py --clear        strip any baked-in snapshot back out

--embed is not the default. See "Before you make this public" in the README.
"""
import csv, io, json, math, re, sys, urllib.request
from collections import Counter, OrderedDict

CSV_URL = 'https://docs.google.com/spreadsheets/d/{}/export?format=csv&gid={}'

# ---------------------------------------------------------------- field helpers
# Enrichment leaves a small vocabulary of "nothing here" markers behind; they are
# not data and must not be counted as a filled cell.
RX_PLACE = re.compile(r'^(unknown|#ref!?|#n/?a|n/?a|na|null|none|nil|tbd|-+|\.+)$', re.I)
# A narrative that opens by denying the thing it was asked about is an absence of
# signal, not a signal. Today's exports carry only positive narratives, but the
# sheets are re-enriched continuously and this is what keeps a future "No, there
# is no evidence of..." from being scored as evidence.
RX_NEG = re.compile(
    r'^\s*[-*\s]*\**\s*(no\b|none\b|not\b|there (are|is) no|'
    r'no (clear|public|direct|confirmed|specific|evidence|signal|indication))', re.I)


def clean(v):
    t = ('' if v is None else str(v)).strip()
    return '' if RX_PLACE.match(t) else t


def norm_txt(v):
    """A signal narrative counts only if it is substantive and affirmative."""
    t = clean(v)
    if not t or len(t) < 12:
        return ''
    return '' if RX_NEG.match(t) else t


def num(v):
    t = clean(v).replace(',', '')
    if not t:
        return None
    try:
        f = float(t)
    except ValueError:
        return None
    return f if f == f and abs(f) != float('inf') else None


def title(s):
    return clean(s) or 'Unknown'


def growth_pct(now, delta):
    """The (nM) columns hold an absolute change; express it against the base it
       grew from. floor(x + .5) because JavaScript rounds halves toward +inf and
       Python rounds them to even — the port has to agree on the boundary."""
    if now is None or delta is None:
        return None
    base = now - delta
    if base <= 0:
        return None
    return math.floor(delta / base * 1000 + 0.5) / 10


# ---------------------------------------------------------------- the signals
# 26 enrichment columns, shared by both workbooks, grouped into the four families
# Capio sells to. Order inside a family runs from the most direct read on a
# purchase to the most circumstantial, so the signal strip in the table reads
# left to right. A column present but never populated in one of the two sheets
# still appears, at zero — an absent signal is a fact about the portfolio.
FAMILIES = OrderedDict([
    ('AI & Copilot Readiness', [
        ('AI presence in Singapore',       'AI Presence In Singapore'),
        ('AI adoption in Singapore',       'AI Adoption In Singapore'),
        ('AI hiring in Singapore',         'AI Hiring Activity Singapore'),
        ('Singapore AI initiatives',       'Singapore AI Initiatives'),
        ('AI infrastructure investment',   'Singapore AI Infrastructure Investment'),
        ('Copilot deployment',             'Copilot Deployment Status'),
    ]),
    ('Workplace & Office', [
        ('Singapore office activity',      'Singapore Office Activity'),
        ('Singapore tech deployments',     'Singapore Tech Deployments'),
        ('Singapore office status',        'Singapore Office Status'),
        ('Singapore office expansion',     'Singapore Office Expansion'),
        ('Workplace technology programme', 'Workplace Technology Initiatives'),
        ('Office / hybrid policy',         'Singapore Office Policy'),
    ]),
    ('IT Modernisation', [
        ('Automation initiatives',         'Singapore Automation Initiatives'),
        ('Digital transformation',         'Digital Transformation Activity'),
        ('Network upgrades',               'Singapore Network Upgrades'),
        ('IT resilience programme',        'IT Resilience Initiatives'),
        ('IT modernisation plans',         'IT Modernisation Plans'),
        ('Cloud adoption',                 'Singapore Cloud Adoption'),
        ('Singapore IT investment',        'Singapore IT Investments'),
        ('Security initiatives',           'Singapore Security Initiatives'),
    ]),
    ('Growth & Funding', [
        ('Singapore regional presence',    'Singapore Regional Presence'),
        ('Singapore market activity',      'Singapore Market Activity'),
        ('Singapore hiring trend',         'Singapore Hiring Trend'),
        ('Funding impact',                 'Singapore Funding Impact'),
        ('Government grant support',       'Singapore Grant Support'),
        ('Workforce expansion',            'Singapore Workforce Expansion'),
    ]),
])
SIGNALS = [pair for fam in FAMILIES.values() for pair in fam]
SIG_LABELS = [lbl for lbl, _ in SIGNALS]
SIX = {lbl: i for i, lbl in enumerate(SIG_LABELS)}
FAM_IX = OrderedDict((fam, [SIX[lbl] for lbl, _ in pairs]) for fam, pairs in FAMILIES.items())
FAM_AI, FAM_WORK, FAM_MOD = (FAM_IX['AI & Copilot Readiness'],
                             FAM_IX['Workplace & Office'],
                             FAM_IX['IT Modernisation'])

# Third-party intent topics that name a device, an operating system or a desktop
# delivery model. These are the topics Capio can quote against directly, and are
# what separates "researching something" from "researching a fleet".
DEVICE_TOPICS = {
    'Laptop', 'Workstations', 'Windows 10', 'Windows 11',
    'AI PC (Artificial Intelligence Personal Computer)',
    'Lenovo ThinkPad', 'Lenovo ThinkCentre', 'Lenovo ThinkBook', 'Lenovo ThinkStation',
    'HP EliteBook', 'Apple MacBook Air', 'Apple MacBook Pro',
    'Desktop as a Service (DaaS)',
}
# Windows 10 went out of support in October 2025. An account researching it — or
# researching what replaces it — has a dated, externally-imposed reason to buy.
EOL_TOPICS = {'Windows 10', 'Windows 11', 'AI PC (Artificial Intelligence Personal Computer)'}


def band_fn(edges, labels):
    """edges ascending; len(labels) == len(edges) + 1"""
    def f(n):
        if n is None:
            return 'Unknown'
        for e, l in zip(edges, labels):
            if n < e:
                return l
        return labels[-1]
    return f


# ---------------------------------------------------------------- the two boards
# The workbooks share 43 of their columns but not their populations, and that is
# the whole reason each board carries its own tests and bands rather than
# inheriting one model.
#
# The existing portfolio is enterprise: ~237 accounts, median 519 staff, third-
# party intent on roughly half of them. The net-new list is Singapore SMB: ~499
# accounts, median 51 staff, and intent on exactly one of them. Scoring net-new
# on "is this account already pricing devices" would put one account in P0 and
# call the ranking done, so it is scored on what that data actually carries.
BOARDS = [
    {
        'key': 'existing', 'label': 'Existing',
        'sheet': '1MJHjM6ubBba_ZHXBk8jsYqLdcixdOBrgxvH8AdZWZYI', 'gid': '0',
        # the name column has been renamed once already; resolve by name and fall
        # back to the first column rather than breaking on the next rename
        'nameCols': ['Company Name',
                     'Existing Accounts - If any — accounts to reuse or prioritise.'],
        'liCols': ['Linkedin URL', 'Company Linkedin URL'],
        'hasIntent': True, 'hasITHC': True,
        'hcBands': ['< 200', '200 – 999', '1,000 – 4,999', '5,000 – 19,999', '20,000+'],
        'hcEdges': [200, 1000, 5000, 20000],
        'itBands': ['< 10', '10 – 49', '50 – 199', '200 – 999', '1,000+'],
        'itEdges': [10, 50, 200, 1000],
        'tests': [
            ('dev', 'Device intent',
             lambda x: bool(x['dev'])),
            ('fleet', 'Fleet demand',
             lambda x: bool(x['sh'] >= 1 or x['s'][SIX['Workforce expansion']]
                            or x['s'][SIX['Singapore hiring trend']]
                            or x['s'][SIX['Singapore office status']]
                            or x['s'][SIX['Singapore office activity']]
                            or (x['ithc'] is not None and x['ithc'] >= 50))),
            ('ai', 'AI programme',
             lambda x: any(x['s'][i] for i in FAM_AI)),
            ('modern', 'Modernisation',
             lambda x: any(x['s'][i] for i in FAM_MOD)),
            ('rollout', 'Rollout announced',
             lambda x: bool(x['s'][SIX['Workplace technology programme']]
                            or x['s'][SIX['Singapore tech deployments']])),
        ],
    },
    {
        'key': 'netnew', 'label': 'Net new',
        'sheet': '1NNFcCsa29lr4gavs7PFyXxm88PLIMpnNTmaIbyKax18', 'gid': '0',
        'nameCols': ['Company Name'],
        'liCols': ['Company Linkedin URL', 'Linkedin URL'],
        # intent is on 1 of 499 rows and IT headcount on 45, so the tests and
        # cards that lean on them are switched off for this board
        'hasIntent': False, 'hasITHC': False,
        'hcBands': ['< 10', '10 – 49', '50 – 99', '100 – 249', '250+'],
        'hcEdges': [10, 50, 100, 250],
        'itBands': ['< 10', '10 – 49', '50 – 199', '200+'],
        'itEdges': [10, 50, 200],
        'tests': [
            ('moment', 'Workplace moment',
             lambda x: any(x['s'][i] for i in FAM_WORK)),
            ('growing', 'Growing',
             lambda x: bool(x['s'][SIX['Singapore hiring trend']] or x['sh'] >= 1
                            or x['gh'] >= 1
                            or (x['g12'] is not None and x['g12'] >= 5))),
            ('ai', 'AI programme',
             lambda x: any(x['s'][i] for i in FAM_AI)),
            ('modern', 'Modernisation',
             lambda x: any(x['s'][i] for i in FAM_MOD)),
            ('scale', 'Fleet worth serving',
             lambda x: bool(x['hc'] is not None and x['hc'] >= 50)),
        ],
    },
]
for _b in BOARDS:
    _b['hcBand'] = band_fn(_b['hcEdges'], _b['hcBands'])
    _b['itBand'] = band_fn(_b['itEdges'], _b['itBands'])
BOARD_OF = {b['key']: b for b in BOARDS}


def tier_with(board, x):
    """Both boards tier on the same shape — five tests, five rules, first match
       wins — so this is one function over whichever five the board defines."""
    A, B, C, D, E = (t[2](x) for t in board['tests'])
    if A and B and C and D:
        return 'P0'
    if (A and B and (C or D or E)) or (B and C and D and E):
        return 'P1'
    if (A and (B or C or D or E)) or (B and (C or D)) or (E and (C or D)):
        return 'P2'
    if sum(x['s']) >= 1 or A:
        return 'P3'
    return 'Unranked'


# ---------------------------------------------------------------- the transform
def derive(board, hdr, rows_in):
    def ix(name):
        i = hdr.index(name) if name in hdr else -1
        if i < 0:
            raise KeyError('missing column: ' + name)
        return i

    def pick(cands, fallback=None):
        for c in cands:
            if c in hdr:
                return hdr.index(c)
        if fallback is not None:
            return fallback
        raise KeyError('missing column: ' + cands[0])

    a = {k: ix(k) for k in [
        'Domain', 'Company HQ', 'Industry', 'Singapore Hiring', 'Global Hiring',
        'Revenue', 'Intent Score', 'Intent Topics',
        'IT Headcount', 'IT HC (3M)', 'IT HC (6M)', 'IT HC (12M)',
        'Company Headcount', 'Company Headcount (3M)', 'Company Headcount (6M)',
        'Company Headcount (12M)']}
    a['name'] = pick(board['nameCols'], 0)
    a['li'] = pick(board['liCols'], -1)
    sig_ix = [ix(col) for _, col in SIGNALS]

    # Domain is the identity each board keys on. Where two rows share one, they
    # are the same company entered twice; the collision is counted, not hidden.
    name_freq, dom_freq = Counter(), Counter()
    for r in rows_in:
        nm = clean(r[a['name']])
        if nm:
            name_freq[nm.lower()] += 1
        dm = clean(r[a['Domain']]).lower()
        if dm:
            dom_freq[dm] += 1

    out, topics_count = [], Counter()
    for r in rows_in:
        if len(r) < len(hdr):
            r = list(r) + [''] * (len(hdr) - len(r))
        name = clean(r[a['name']])
        if not name:
            continue
        dom = clean(r[a['Domain']]).lower()

        s = [1 if norm_txt(r[i]) else 0 for i in sig_ix]

        ints = int(num(r[a['Intent Score']]) or 0)
        tps = [t.strip() for t in clean(r[a['Intent Topics']]).split(',') if t.strip()]
        for t in tps:
            topics_count[t] += 1

        gh = int(num(r[a['Global Hiring']]) or 0)
        sh = int(num(r[a['Singapore Hiring']]) or 0)

        hc = num(r[a['Company Headcount']])
        g3 = growth_pct(hc, num(r[a['Company Headcount (3M)']]))
        g6 = growth_pct(hc, num(r[a['Company Headcount (6M)']]))
        g12 = growth_pct(hc, num(r[a['Company Headcount (12M)']]))
        ithc = num(r[a['IT Headcount']])
        itg3 = growth_pct(ithc, num(r[a['IT HC (3M)']]))
        itg6 = growth_pct(ithc, num(r[a['IT HC (6M)']]))
        itg12 = growth_pct(ithc, num(r[a['IT HC (12M)']]))

        rec = {
            'n': name, 'd': dom, 'ind': title(r[a['Industry']]),
            'hq': title(r[a['Company HQ']]),
            'bnd': board['hcBand'](hc), 'itb': board['itBand'](ithc),
            'hc': None if hc is None else int(hc),
            'ithc': None if ithc is None else int(ithc),
            'rev': num(r[a['Revenue']]),
            'g3': g3, 'g6': g6, 'g12': g12,
            'itg3': itg3, 'itg6': itg6, 'itg12': itg12,
            'is': ints, 'nt': len(tps), 't': tps,
            'dev': 1 if (set(tps) & DEVICE_TOPICS) else 0,
            'eol': 1 if (set(tps) & EOL_TOPICS) else 0,
            'sh': sh, 'gh': gh,
            'li': 1 if (a['li'] >= 0 and clean(r[a['li']])) else 0,
            'dn': 1 if name_freq[name.lower()] > 1 else 0,
            'dd': 1 if (dom and dom_freq[dom] > 1) else 0,
            's': s,
        }
        rec['pri'] = tier_with(board, rec)
        out.append(rec)

    # the same company listed twice under two legal names: same domain, two rows
    dupes = sorted([dm, sorted({x['n'] for x in out if x['d'] == dm})]
                   for dm, c in dom_freq.items() if c > 1)
    return out, topics_count, len(rows_in), dupes


def build(board, acc_csv):
    A = [r for r in csv.reader(io.StringIO(acc_csv.lstrip('﻿')))
         if any(c.strip() for c in r)]
    if len(A) < 2:
        raise ValueError('empty sheet export')
    hdr = [h.strip() for h in A[0]]     # some headers carry trailing spaces
    rows, topics_count, given, dupes = derive(board, hdr, A[1:])

    # ---- compaction: intern the categoricals, emit positional rows ----------
    dicts = {}

    def intern(key, val):
        d = dicts.setdefault(key, {'list': [], 'ix': {}})
        if val not in d['ix']:
            d['ix'][val] = len(d['list'])
            d['list'].append(val)
        return d['ix'][val]

    COLS = ['n', 'd', 'ind', 'hq', 'bnd', 'itb', 'hc', 'ithc', 'rev', 'g3', 'g6', 'g12',
            'itg3', 'itg6', 'itg12', 'is', 'nt', 'dev', 'eol', 'sh', 'gh', 'li',
            'pri', 'dn', 'dd', 's', 't']
    CATS = {'ind': 'ind', 'hq': 'hq', 'bnd': 'bnd', 'itb': 'itb', 'pri': 'pri'}
    packed = [[intern(CATS[c], r[c]) if c in CATS
               else [intern('topic', t) for t in r[c]] if c == 't'
               else r[c] for c in COLS] for r in rows]

    n = len(rows)
    cnt = lambda f: sum(1 for x in rows if f(x))
    fam = lambda k: cnt(lambda x: any(x['s'][i] for i in FAM_IX[k]))
    distinct = len({x['d'] for x in rows if x['d']}) + cnt(lambda x: not x['d'])
    cov = {
        'given': given, 'rows': n, 'distinct': distinct,
        'domain': cnt(lambda x: bool(x['d'])),
        'li': cnt(lambda x: x['li']),
        'signal': cnt(lambda x: sum(x['s']) > 0),
        'intent': cnt(lambda x: x['is'] > 0),
        'device': cnt(lambda x: x['dev']),
        'eol': cnt(lambda x: x['eol']),
        'hc': cnt(lambda x: x['hc'] is not None),
        'ithc': cnt(lambda x: x['ithc'] is not None),
        'rev': cnt(lambda x: x['rev'] is not None),
        'firmo': cnt(lambda x: x['ind'] != 'Unknown' and x['hq'] != 'Unknown'),
        'sgp': cnt(lambda x: x['s'][SIX['Singapore regional presence']]
                   or x['s'][SIX['Singapore market activity']]
                   or x['hq'] == 'Singapore'),
        'dupname': cnt(lambda x: x['dn']),
        'dupdom': cnt(lambda x: x['dd']),
        'ai': fam('AI & Copilot Readiness'), 'work': fam('Workplace & Office'),
        'mod': fam('IT Modernisation'), 'grow': fam('Growth & Funding'),
    }
    # how much of each test the board could even evaluate
    test_hits = {k: cnt(f) for k, _, f in board['tests']}

    return {
        'board': board['key'],
        'dict': {k: v['list'] for k, v in dicts.items()},
        'accounts': {'cols': COLS, 'rows': packed, 'n': n},
        'summary': {
            'signals': SIG_LABELS,
            'families': [[fam_, ix_] for fam_, ix_ in FAM_IX.items()],
            'hcBands': board['hcBands'], 'itBands': board['itBands'],
            'deviceTopics': sorted(DEVICE_TOPICS), 'eolTopics': sorted(EOL_TOPICS),
            'topics': topics_count.most_common(25),
            'dupes': dupes, 'cov': cov, 'testHits': test_hits,
        },
    }


# ---------------------------------------------------------------- io / reporting
def fetch(board):
    url = CSV_URL.format(board['sheet'], board['gid'])
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode('utf-8', 'replace')
    if body.lstrip()[:200].lower().startswith(('<!doctype html', '<html')):
        raise SystemExit(f'{board["label"]}: the sheet returned a sign-in page — '
                         'check that it is link-viewable')
    return body


def report(board, data):
    s, cov = data['summary'], data['summary']['cov']
    rows, cols = data['accounts']['rows'], data['accounts']['cols']
    ci = {c: i for i, c in enumerate(cols)}
    pri_list = data['dict']['pri']
    n = cov['rows']
    pc = lambda x: f'{x / n * 100:.1f}%' if n else '—'

    print(f'\n{board["label"]} — {n:,} accounts   ({board["sheet"]})')
    print('=' * 68)
    tally = Counter(pri_list[r[ci['pri']]] for r in rows)
    means = {}
    for p in ['P0', 'P1', 'P2', 'P3', 'Unranked']:
        grp = [sum(r[ci['s']]) for r in rows if pri_list[r[ci['pri']]] == p]
        means[p] = sum(grp) / len(grp) if grp else 0.0
    print('  priority tiers')
    for p in ['P0', 'P1', 'P2', 'P3', 'Unranked']:
        print(f'    {p:<10} {tally[p]:>6,}   {tally[p] / n * 100:5.1f}%'
              f'   mean signals {means[p]:5.2f}')
    mono = all(means[a] >= means[b] for a, b in
               zip(['P0', 'P1', 'P2', 'P3'], ['P1', 'P2', 'P3', 'Unranked']))
    print(f'    {"ordering holds" if mono else "*** ORDERING BROKEN ***"}'
          '  (mean signal count must fall with every tier)')

    print('\n  the five tests')
    for k, label, _ in board['tests']:
        v = s['testHits'][k]
        print(f'    {label:<24} {v:>6,}   {pc(v)}')

    print('\n  coverage')
    items = [('domain resolved', 'domain'), ('LinkedIn URL', 'li'),
             ('carries a signal', 'signal'), ('company headcount', 'hc'),
             ('reported revenue', 'rev'), ('Singapore footprint', 'sgp')]
    if board['hasIntent']:
        items += [('third-party intent', 'intent'), ('device-level intent', 'device'),
                  ('Windows / AI PC intent', 'eol')]
    if board['hasITHC']:
        items += [('IT headcount', 'ithc')]
    for lbl, k in items:
        print(f'    {lbl:<24} {cov[k]:>6,}   {pc(cov[k])}')

    print('\n  signal prevalence')
    for i, lbl in enumerate(s['signals']):
        c = sum(r[ci['s']][i] for r in rows)
        print(f'    {lbl:<32} {c:>6,}   {pc(c)}')

    dist = Counter(sum(r[ci['s']]) for r in rows)
    print('\n  signals per account    ' + '  '.join(f'{k}:{dist[k]}' for k in sorted(dist)))
    if s['dupes']:
        print(f'\n  {n:,} rows resolve to {cov["distinct"]:,} distinct companies '
              f'— {len(s["dupes"])} domains appear twice:')
        for dm, names in s['dupes']:
            print(f'    {dm:<28} {" / ".join(names)}')
    print()


MARK_A = '\nconst SNAPSHOT =\n'
MARK_B = '\nconst SNAPSHOT_AT = '


def rewrite_snapshot(payload, at):
    import pathlib
    p = pathlib.Path(__file__).with_name('index.html')
    src = p.read_text(encoding='utf-8')
    i = src.index(MARK_A)
    j = src.index(MARK_B, i)
    k = src.index(';\n', j)
    out = src[:i] + MARK_A + payload + ';' + MARK_B + at + src[k + 1:]
    p.write_text(out, encoding='utf-8')
    return p


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--clear' in args:
        p = rewrite_snapshot('null', 'null')
        print(f'cleared the embedded snapshot in {p.name}')
        raise SystemExit(0)

    only = None
    if '--board' in args:
        only = args[args.index('--board') + 1]
        if only not in BOARD_OF:
            raise SystemExit(f'unknown board {only!r}; expected one of '
                             + ', '.join(BOARD_OF))
    todo = [b for b in BOARDS if only is None or b['key'] == only]

    built = {}
    for b in todo:
        built[b['key']] = build(b, fetch(b))
        report(b, built[b['key']])

    if '--embed' in args:
        if only:
            raise SystemExit('--embed writes both boards; drop --board')
        from datetime import datetime, timezone
        at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        p = rewrite_snapshot(json.dumps(built, separators=(',', ':')), json.dumps(at))
        total = sum(v['accounts']['n'] for v in built.values())
        print(f'embedded {total:,} accounts across {len(built)} boards into {p.name}')
        print('this publishes both lists into the repo — see the README before pushing')
