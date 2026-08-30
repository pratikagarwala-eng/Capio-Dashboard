#!/usr/bin/env python3
"""
Capio International — Account Intelligence: the canonical derivation.

This file is the statement of record for how the dashboard turns the Google
Sheet into the boards it draws. `buildData()` inside index.html is a direct port
of it; run this and compare its report against the page — they must agree.

    python3 build_data.py            derive and report, write nothing
    python3 build_data.py --embed    also bake the result into index.html
    python3 build_data.py --clear    strip any baked-in snapshot back out

--embed is not the default. See "Before you make this public" in the README.
"""
import csv, io, json, re, sys, urllib.request
from collections import Counter, OrderedDict

SHEET_ID = '1MJHjM6ubBba_ZHXBk8jsYqLdcixdOBrgxvH8AdZWZYI'
TAB_GID = {'accounts': '0'}
CSV_URL = 'https://docs.google.com/spreadsheets/d/{}/export?format=csv&gid={}'

# ---------------------------------------------------------------- field helpers
# Enrichment leaves a small vocabulary of "nothing here" markers behind; they are
# not data and must not be counted as a filled cell.
RX_PLACE = re.compile(r'^(unknown|#ref!?|#n/?a|n/?a|na|null|none|nil|tbd|-+|\.+)$', re.I)
# A narrative that opens by denying the thing it was asked about is an absence of
# signal, not a signal. Today's export carries only positive narratives, but the
# sheet is re-enriched continuously and this is what keeps a future "No, there is
# no evidence of..." from being scored as evidence.
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


# ---------------------------------------------------------------- the signals
# 25 enrichment columns, grouped into the four families Capio actually sells to.
# Order inside a family runs from the most direct read on a purchase to the most
# circumstantial, so the signal strip in the table is read left to right.
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
# family name -> the signal indices it owns, so the browser can group without
# re-stating the taxonomy
FAM_IX = OrderedDict((fam, [SIX[lbl] for lbl, _ in pairs]) for fam, pairs in FAMILIES.items())

# Third-party intent topics that name a device, an operating system or a desktop
# delivery model. These are the topics Capio can quote against directly, and they
# are what separates "researching something" from "researching a fleet".
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

# ---------------------------------------------------------------- banding
# The portfolio runs from 2 staff to 150,832, so the bands are logarithmic rather
# than even. Company headcount sizes the fleet; IT headcount sizes both the buying
# committee and the team that would run a deployment.
HC_BANDS = ['< 200', '200 – 999', '1,000 – 4,999', '5,000 – 19,999', '20,000+']


def hc_band(n):
    if n is None:
        return 'Unknown'
    if n < 200:
        return '< 200'
    if n < 1000:
        return '200 – 999'
    if n < 5000:
        return '1,000 – 4,999'
    if n < 20000:
        return '5,000 – 19,999'
    return '20,000+'


IT_BANDS = ['< 10', '10 – 49', '50 – 199', '200 – 999', '1,000+']


def it_band(n):
    if n is None:
        return 'Unknown'
    if n < 10:
        return '< 10'
    if n < 50:
        return '10 – 49'
    if n < 200:
        return '50 – 199'
    if n < 1000:
        return '200 – 999'
    return '1,000+'


REV_BANDS = [('< $10M', 0, 1e7), ('$10 – 100M', 1e7, 1e8), ('$100M – 1B', 1e8, 1e9),
             ('$1 – 10B', 1e9, 1e10), ('$10B+', 1e10, float('inf'))]


def growth_pct(now, delta):
    """The (nM) columns hold an absolute change; express it against the base it
       grew from. floor(x + .5) because JavaScript rounds halves toward +inf and
       Python rounds them to even — the port has to agree on the boundary."""
    if now is None or delta is None:
        return None
    base = now - delta
    if base <= 0:
        return None
    import math
    return math.floor(delta / base * 1000 + 0.5) / 10


# ---------------------------------------------------------------- the transform
def derive(hdr, rows_in):
    def ix(name):
        i = hdr.index(name) if name in hdr else -1
        if i < 0:
            raise KeyError('missing column: ' + name)
        return i

    NAME = hdr[0]   # "Existing Accounts - If any — ..." — the account name column
    a = {k: ix(k) for k in [
        'Domain', 'Company HQ', 'Industry', 'Singapore Hiring', 'Global Hiring',
        'Linkedin URL', 'Revenue', 'Intent Score', 'Intent Topics',
        'IT Headcount', 'IT HC (3M)', 'IT HC (6M)', 'IT HC (12M)',
        'Company Headcount', 'Company Headcount (3M)', 'Company Headcount (6M)',
        'Company Headcount (12M)']}
    a['name'] = ix(NAME)
    sig_ix = [ix(col) for _, col in SIGNALS]

    # Domain is the identity the whole dashboard keys on. Names repeat and are
    # inconsistently cased in this sheet; domains do not.
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
        nsig = sum(s)

        ints = int(num(r[a['Intent Score']]) or 0)
        tps = [t.strip() for t in clean(r[a['Intent Topics']]).split(',') if t.strip()]
        for t in tps:
            topics_count[t] += 1

        hq = title(r[a['Company HQ']])
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

        dev = 1 if (set(tps) & DEVICE_TOPICS) else 0
        eol = 1 if (set(tps) & EOL_TOPICS) else 0

        # ---- the five tests the priority tiers are built from ----------------
        # A  a device-level purchase is already being researched
        A = bool(dev)
        # B  there is a fleet to serve, and something is moving it: local hiring,
        #    a workforce or office change, or an IT org big enough to run a rollout
        B = bool(sh >= 1 or s[SIX['Workforce expansion']] or s[SIX['Singapore hiring trend']]
                 or s[SIX['Singapore office status']] or s[SIX['Singapore office activity']]
                 or (ithc is not None and ithc >= 50))
        # C  an AI programme is live — the AI PC and Copilot-device conversation
        C = any(s[i] for i in FAM_IX['AI & Copilot Readiness'])
        # D  an IT modernisation programme is live — services and the LGA cross-sell
        D = any(s[i] for i in FAM_IX['IT Modernisation'])
        # E  a workplace or deployment programme has been announced
        E = bool(s[SIX['Workplace technology programme']] or s[SIX['Singapore tech deployments']])

        if A and B and C and D:
            pri = 'P0'
        elif (A and B and (C or D or E)) or (B and C and D and E):
            pri = 'P1'
        elif (A and (B or C or D or E)) or (B and (C or D)) or (E and (C or D)):
            pri = 'P2'
        elif nsig >= 1 or A:
            pri = 'P3'
        else:
            pri = 'Unranked'

        out.append({
            'n': name, 'd': dom, 'ind': title(r[a['Industry']]), 'hq': hq,
            'bnd': hc_band(hc), 'itb': it_band(ithc),
            'hc': None if hc is None else int(hc),
            'ithc': None if ithc is None else int(ithc),
            'rev': num(r[a['Revenue']]),
            'g3': g3, 'g6': g6, 'g12': g12,
            'itg3': itg3, 'itg6': itg6, 'itg12': itg12,
            'is': ints, 'nt': len(tps), 't': tps,
            'dev': dev, 'eol': eol,
            'sh': sh, 'gh': gh,
            'li': 1 if clean(r[a['Linkedin URL']]) else 0,
            'pri': pri,
            'dn': 1 if name_freq[name.lower()] > 1 else 0,
            'dd': 1 if (dom and dom_freq[dom] > 1) else 0,
            's': s,
        })
    # the same company listed twice under two legal names: same domain, same
    # headcount, two rows. Named here so the dashboard can show them rather than
    # quietly counting one company as two accounts.
    dupes = []
    for dm, c in dom_freq.items():
        if c > 1:
            dupes.append([dm, sorted({x['n'] for x in out if x['d'] == dm})])
    dupes.sort()
    return out, topics_count, len(rows_in), dupes


def build(acc_csv):
    A = [r for r in csv.reader(io.StringIO(acc_csv.lstrip('﻿'))) if any(c.strip() for c in r)]
    if len(A) < 2:
        raise ValueError('empty sheet export')
    hdr = [h.strip() for h in A[0]]     # the source headers carry trailing spaces
    rows, topics_count, given, dupes = derive(hdr, A[1:])

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
    # rows are not companies: five domains appear twice under two legal names
    distinct = len({x['d'] for x in rows if x['d']}) + sum(1 for x in rows if not x['d'])
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
        'dupname': cnt(lambda x: x['dn']),
        'dupdom': cnt(lambda x: x['dd']),
        'ai': cnt(lambda x: any(x['s'][i] for i in FAM_IX['AI & Copilot Readiness'])),
        'mod': cnt(lambda x: any(x['s'][i] for i in FAM_IX['IT Modernisation'])),
        'work': cnt(lambda x: any(x['s'][i] for i in FAM_IX['Workplace & Office'])),
        'grow': cnt(lambda x: any(x['s'][i] for i in FAM_IX['Growth & Funding'])),
    }

    return {
        'dict': {k: v['list'] for k, v in dicts.items()},
        'accounts': {'cols': COLS, 'rows': packed, 'n': n},
        'summary': {
            'signals': SIG_LABELS,
            'families': [[fam, ix] for fam, ix in FAM_IX.items()],
            'hcBands': HC_BANDS, 'itBands': IT_BANDS,
            'deviceTopics': sorted(DEVICE_TOPICS), 'eolTopics': sorted(EOL_TOPICS),
            'topics': topics_count.most_common(25),
            'dupes': dupes,
            'cov': cov,
        },
    }


# ---------------------------------------------------------------- io / reporting
def fetch(tab='accounts'):
    url = CSV_URL.format(SHEET_ID, TAB_GID[tab])
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode('utf-8', 'replace')
    if body.lstrip()[:200].lower().startswith(('<!doctype html', '<html')):
        raise SystemExit('the sheet returned a sign-in page — check that it is link-viewable')
    return body


def report(data):
    s, cov = data['summary'], data['summary']['cov']
    rows = data['accounts']['rows']
    cols = data['accounts']['cols']
    ci = {c: i for i, c in enumerate(cols)}
    pri_list = data['dict']['pri']
    n = cov['rows']
    pc = lambda x: f'{x / n * 100:.1f}%' if n else '—'

    print(f'\nCapio International — account intelligence')
    print(f'{"=" * 62}')
    print(f'  rows in sheet          {cov["given"]:>6,}')
    print(f'  accounts derived       {cov["rows"]:>6,}')
    print(f'\n  priority tiers')
    tally = Counter(pri_list[r[ci["pri"]]] for r in rows)
    for p in ['P0', 'P1', 'P2', 'P3', 'Unranked']:
        print(f'    {p:<10} {tally[p]:>6,}   {tally[p] / n * 100:5.1f}%')
    print(f'\n  coverage')
    for lbl, k in [('domain resolved', 'domain'), ('LinkedIn URL', 'li'),
                   ('carries a signal', 'signal'), ('third-party intent', 'intent'),
                   ('device-level intent', 'device'), ('Windows / AI PC intent', 'eol'),
                   ('company headcount', 'hc'), ('IT headcount', 'ithc'),
                   ('reported revenue', 'rev')]:
        print(f'    {lbl:<24} {cov[k]:>6,}   {pc(cov[k])}')
    print(f'\n  signal families')
    for lbl, k in [('AI & Copilot Readiness', 'ai'), ('Workplace & Office', 'work'),
                   ('IT Modernisation', 'mod'), ('Growth & Funding', 'grow')]:
        print(f'    {lbl:<24} {cov[k]:>6,}   {pc(cov[k])}')
    print(f'\n  signal prevalence')
    for i, lbl in enumerate(s['signals']):
        c = sum(r[ci['s']][i] for r in rows)
        print(f'    {lbl:<32} {c:>6,}   {pc(c)}')
    dist = Counter(sum(r[ci['s']]) for r in rows)
    print(f'\n  signals per account    ' + '  '.join(
        f'{k}:{dist[k]}' for k in sorted(dist)))
    if s['dupes']:
        print(f'\n  {cov["rows"]:,} rows resolve to {cov["distinct"]:,} distinct companies '
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
    args = set(sys.argv[1:])
    if '--clear' in args:
        p = rewrite_snapshot('null', 'null')
        print(f'cleared the embedded snapshot in {p.name}')
        raise SystemExit(0)
    data = build(fetch('accounts'))
    report(data)
    if '--embed' in args:
        from datetime import datetime, timezone
        at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        p = rewrite_snapshot(json.dumps(data, separators=(',', ':')), json.dumps(at))
        print(f'embedded {data["accounts"]["n"]:,} accounts into {p.name}')
        print('this publishes the portfolio into the repo — see the README before pushing')
