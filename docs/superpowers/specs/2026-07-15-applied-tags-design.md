# Applied tags — design

2026-07-15. Feature: mark roles as "Applied" while browsing the board, shared
between the two users, plus a mobile-responsive layout.

## Requirements (decided with Samy)

- Tags are **shared**: either person tags a role, the other sees it.
- Access via **private link**: the public URL shows a clean board with no tag
  UI; a link with a secret in the URL fragment (`#k=<secret>&me=<name>`)
  enables viewing and editing tags. The fragment never reaches server logs.
- Attribution: a tag records who set it (`me` param) and when.
- v1 has a single state: Applied (schema supports arbitrary status strings).
- Board must be usable on mobile (stacked cards instead of the wide table).

## Architecture

GitHub Pages stays fully static. Shared state lives in a dedicated free
Supabase project (`pmm-job-board`, ref `wvtlhnyfgjkuontmpgoy`, Samy's personal
org) — chosen over a Cloudflare Worker (new infra) and GitHub-as-database
(token in the link, commit per click).

### Database

- `public.pmm_job_tags(job_key text pk, status text, tagged_by text, tagged_at timestamptz)`
  — RLS enabled, **no policies**, all direct anon access revoked.
- `private.pmm_config(k, v)` holds the shared secret (`k='secret'`); the
  `private` schema is not exposed through the API.
- Two `security definer` RPCs are the only surface, both `EXECUTE`-granted to
  `anon` and both raising `forbidden` unless the passed secret matches:
  - `pmm_get_tags(p_secret)` → all tags
  - `pmm_set_tag(p_secret, p_job_key, p_status, p_who)` → upsert, or delete
    when `p_status` is null (also length-caps inputs)
- The anon key in the page is public by design; it only reaches these RPCs.
- The secret is *not* in the repo. It lives in the deployed Supabase config
  and in the private links file shared between the two users.

### Job identity

`state_key(source_url)` from `refresh.py` (already survives daily refreshes,
host variants, and slug changes) is embedded per row as `key` in the page
data by `build_html.py`. Tags for delisted roles simply stop being rendered;
rows are never deleted server-side.

### Frontend (`build_html.py` template)

- `#k` present → `body.tagging` class reveals an Applied column (toggle
  button + "who · date" meta), a "Hide applied" filter chip, and an applied
  count. Applied rows render dimmed.
- Optimistic toggle: UI flips immediately, `pmm_set_tag` runs async; on
  failure the change reverts and a toast explains.
- `#k` absent (public view): no tag UI at all, board unchanged.
- Wrong key: toast, tag UI removed, board still browsable.

### Mobile (≤720px)

Table switches to stacked flex cards (role first, then company, meta badges,
prominent Apply button, full-width tap target for the toggle). Sorting stays a
desktop-only affordance; mobile keeps the newest-first default plus search.

## Testing performed

Headless-browser E2E on the built page: tag → attribution meta renders →
persists across reload (server round-trip) → hide-applied filter counts →
untag deletes server-side. RPC auth checked directly: wrong secret and direct
table reads both rejected. Mobile (375×812) and desktop (1280×800)
screenshots reviewed.
