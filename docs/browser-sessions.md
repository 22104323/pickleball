# Browser sessions on Vercel

The hosted entry page uses the original green Courtside organizer interface. It
loads `browser-engine.js` before `app.js`; its `data-runtime="browser"` selects
browser execution. The existing Python/SQLite organizer stays available locally
through `python3 -m picklequeue.server` and `web/organizer.html`.

## User flow

1. Select **Generate Link** on the landing page. A new isolated Open Play session
   is created on the device, with an expiry 48 hours after creation.
2. Use **Copy link** or **Open Courtside**. The generated URL contains a compressed
   session snapshot in its fragment. No roster/session payload is uploaded to the
   app server. Anyone with the link can open its snapshot.
3. Use **New session** to choose courts, capacity, and a play format; each new
   session gets its own token and independent ratings/history. Import players
   manually or through the **Reclub link** tab, review them, and check them in.
4. Queue assignment, pairing, game starts, winners, corrections, results, and
   Glicko-2 close run in browser JavaScript. Mutations reread browser storage under
   a Web Lock and compare the session revision. Failed changes are not saved.
5. The header's **Copy link** exports the current snapshot. Recipients open a copy;
   edits do not synchronize across phones. Existing copies in the same browser
   keep their latest local changes instead of being overwritten by an old snapshot.
6. The app rejects an expired session and returns to the landing page. Generate
   another link for a fresh session. Expired local records are removed when accessed
   or when the landing page/new-session flow performs cleanup.

## Storage and limits

Session data stays in browser `localStorage`, scoped by the random session token.
Clearing site data removes the local copy; a previously copied, unexpired snapshot
can still be opened. No hosted database, account, paid service, or Socket.IO server
is used. A session has at most 200 roster entries; link imports/exports have a 2 MB
uncompressed limit to bound decompression and browser memory usage. Links can grow
with the roster and game history, and messaging services may impose shorter limits.

Expiry is enforced by the browser app. It is not server-enforced revocation or a
security guarantee against a recipient retaining data, changing their browser
clock, or modifying client code. The copied URL contains participant data; share
it only with intended recipients. Live shared editing remains separate work.

## Reclub imports

The browser validates public HTTPS `reclub.co/m/{reference}` links, then fetches
`https://api.reclub.co/meets/by-ref/{reference}` and account profiles in batches of
50. Requests omit credentials, reject redirects, and have a 10-second timeout.
Only status 1 slots are reviewed. Account holders use their profiles; named
friend slots use their supplied names; unnamed guests keep neutral labels and
separate slot identities. RSVP never becomes a physical check-in automatically.
No HTML scraping, group discovery, app-server proxy, or fixed `RECLUB_EVENT_REF`
is needed. A Reclub failure is reported in the import dialog; manual import remains
available. Its public API and CORS behavior are compatibility observations, not a
supported developer contract or service guarantee.

## Deployment

Vercel publishes `web/`, with `api/` and the local organizer page excluded by
`.vercelignore`. The retired attendee script is also excluded. CSP permits direct
connections to `https://api.reclub.co`. Preflight checks the browser runtime wiring
and exclusions; it does not prove matching correctness or a successful deployment.

Use the repository's protected PR and GitHub environment workflow. Required settings
remain `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`, optional `VERCEL_TEAM_ID`, and
`VERCEL_WEBSITE_READY=true`. The already deployed attendee page remains live until
an actual deployment of the corrected commit reports READY and is inspected.
