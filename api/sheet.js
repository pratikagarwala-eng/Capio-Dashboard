/**
 * Edge proxy for the source Google Sheet.
 *
 * Two reasons this exists rather than the page fetching Google directly:
 *   - the spreadsheet id stays server-side, so it never reaches a viewer;
 *   - the response is cached at the edge, so N concurrent viewers cost one
 *     upstream read per minute instead of N.
 *
 * SHEET_ID in the Vercel project's environment variables overrides the workbook
 * this reads. It is optional: without it the proxy falls back to DEFAULT_SHEET_ID
 * below, so a fresh import deploys and works with no configuration step. That
 * default costs nothing — build_data.py and the README already carry the same id
 * in plain text, and the sheet has to be link-viewable for this to read it at all.
 * Set the variable to point a deployment at a different workbook.
 *
 * Opening the file from disk or serving it statically still works — pass
 * ?sheet=<id> on the page URL and it reads Google directly instead.
 */
export const config = { runtime: 'edge' };

const DEFAULT_SHEET_ID = '1MJHjM6ubBba_ZHXBk8jsYqLdcixdOBrgxvH8AdZWZYI';
const TAB_GID = { accounts: '0' };
const UPSTREAM_TIMEOUT_MS = 20000;

const fail = (status, msg) =>
  new Response(msg, {
    status,
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
  });

export default async function handler(req) {
  const gid = TAB_GID[new URL(req.url).searchParams.get('tab')];
  if (!gid) return fail(400, 'unknown tab');

  const id = process.env.SHEET_ID || DEFAULT_SHEET_ID;
  // the id reaches us from configuration, not from the request, but a malformed
  // one would still be pasted straight into an outbound URL
  if (!/^[A-Za-z0-9_-]{20,100}$/.test(id)) return fail(500, 'SHEET_ID is malformed');

  const upstream =
    `https://docs.google.com/spreadsheets/d/${id}/export?format=csv&gid=${gid}`;

  let res;
  try {
    res = await fetch(upstream, {
      headers: { 'user-agent': 'Mozilla/5.0' },
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (err) {
    return fail(504, `could not reach the sheet: ${err.name}`);
  }
  if (!res.ok) return fail(502, `sheet responded ${res.status}`);

  /* When link sharing is switched off, Google answers 200 with an HTML sign-in
     page. Passing that through would hand the browser a "CSV" that parses into
     garbage and silently repaints the dashboard with nonsense, so check the
     body before trusting it. */
  const body = await res.text();
  const head = body.slice(0, 200).trimStart().toLowerCase();
  if (head.startsWith('<!doctype html') || head.startsWith('<html')) {
    return fail(502, 'the sheet returned a sign-in page — check that it is link-viewable');
  }

  return new Response(body, {
    headers: {
      'content-type': 'text/csv; charset=utf-8',
      // one upstream read a minute; keep serving the last copy for an hour if
      // Google is slow or briefly unavailable
      'cache-control': 's-maxage=60, stale-while-revalidate=3600',
      'x-content-type-options': 'nosniff',
    },
  });
}
