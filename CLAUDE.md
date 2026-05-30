# CLAUDE.md — Valeraup Engineering Standards

This file is the working engineering guide for the **Valeraup** repository. It is
read by every agent (and human) before they touch the code. It encodes the
mandatory standards from the agreed spec (section 13) and ties them to the
**actual** layout of this repo. When a rule here conflicts with a quick
shortcut, the rule wins.

> **What Valeraup is, in one sentence:** a manager photographs a supplier invoice
> on a phone (PWA), Gemini 2.5 Flash Vision extracts line items, the system maps
> supplier SKUs to our SalesDrive catalog SKUs (auto if remembered, manual
> otherwise — and remembers it), then generates an `.xlsx` receipt for manual
> import into SalesDrive (`Склад → Надходження → Імпорт`).

---

## 1. Repository layout (the real tree)

Absolute root: `/Users/nextcrm/Desktop/Projects/valeraup`

```
valeraup/
├── CLAUDE.md                  ← you are here (engineering standards)
├── README.md                  ← what/why, setup, local start, tests, deploy
├── docker-compose.yml         ← DEV: 5 services (db, redis, backend, worker+beat -B, frontend)
├── docker-compose.prod.yml    ← PROD: db, redis, backend(gunicorn), worker, beat (split), frontend(nginx)
├── .env.prod.example          ← prod env template (never commit .env.prod)
├── .gitignore  .dockerignore
├── .github/workflows/ci.yml   ← backend (check + pytest) + frontend (tsc + build) jobs
│
├── docs/
│   ├── ARCHITECTURE.md        ← components, data flow, Mermaid flow + state diagrams
│   ├── INTEGRATIONS.md        ← SalesDrive (YML export, .xlsx import) + Gemini (prompt/JSON)
│   └── MAPPING.md             ← normalization rules, lookup, auto vs manual, learning
│
├── backend/
│   ├── manage.py              ← sets DJANGO_SETTINGS_MODULE=valeraup.settings
│   ├── requirements.txt       ← pinned deps (+ Pillow, whitenoise; dev/test under a comment)
│   ├── pytest.ini             ← DJANGO_SETTINGS_MODULE=valeraup.settings
│   ├── conftest.py            ← shared pytest fixtures
│   ├── Dockerfile             ← python:3.12-slim; CMD = entrypoint.sh
│   ├── entrypoint.sh          ← prod boot: migrate → collectstatic → exec gunicorn
│   ├── .env.example           ← safe placeholders, never real keys
│   ├── valeraup/              ← project package
│   │   ├── settings.py  urls.py  celery.py  __init__.py (imports celery_app)
│   │   └── wsgi.py  asgi.py
│   ├── integrations/          ← external boundaries (NOT Django apps)
│   │   ├── gemini.py          ← recognize_invoice() (real google-genai call), SYSTEM_PROMPT
│   │   └── salesdrive.py      ← fetch_catalog_yml(), parse_catalog_yml() (namespace-tolerant)
│   ├── apps/                  ← the 5 domain apps (AppConfig.name = "apps.<x>")
│   │   ├── accounts/          ← Profile (role, pin_hash); auth (login/refresh/pin/me/set-pin)
│   │   │   ├── signals.py     ← post_save → auto Profile(role='operator')
│   │   │   └── permissions.py ← IsAdmin / IsOperatorOrAdmin (keyed on profile.role)
│   │   ├── suppliers/         ← Supplier; SupplierViewSet (DRF router; operators read, admins mutate)
│   │   ├── catalog/           ← OurProduct + IntegrationSettings (singleton) + services.sync_catalog/probe_catalog_yml + tasks
│   │   │   └── management/commands/sync_catalog.py ← CLI catalog sync
│   │   ├── mapping/           ← ArticleMapping + services (normalize/match/remember) + ArticleMappingViewSet (/api/mappings/ admin CRUD)
│   │   └── receipts/          ← Receipt/ReceiptPhoto(image+image_url)/ReceiptLine
│   │       ├── services/xlsx.py   ← build_receipt_xlsx (4 cols, group + weighted price)
│   │       ├── services/status.py ← recompute_receipt_status / set_receipt_status
│   │       └── tasks.py           ← recognize_receipt_task (reads photo bytes from storage)
│   └── tests/                 ← test_accounts, test_catalog, test_mapping, test_receipts,
│                                 test_upload, test_xlsx, test_models, test_api_smoke
│
└── frontend/                  ← React 19 + Vite + TS PWA + Capacitor + Storybook
    ├── package.json  vite.config.ts  tsconfig*.json  capacitor.config.ts
    ├── index.html  nginx.conf  Dockerfile  .env.example
    ├── public/                ← manifest.webmanifest, robots.txt, icons/
    ├── .storybook/            ← main.ts, preview.ts (light/dark theme toolbar; imports tokens.css)
    └── src/
        ├── main.tsx  App.tsx  router.tsx  vite-env.d.ts
        ├── styles/            ← tokens.css (light + [data-theme='dark'] + glass), global.css
        ├── lib/               ← cn.ts, api.ts (JWT fetch + postForm), auth.tsx, camera.ts, useTheme.ts
        ├── types/index.ts     ← mirrors backend models + request/response shapes
        ├── components/
        │   ├── ThemeProvider.tsx  ← theme context + ThemeToggle (Sun/Moon)
        │   ├── ui/            ← Button, Input, Card, Sheet, Spinner, Skeleton, EmptyState,
        │   │                     Toast/Toaster/useToast, StatusBadge (+ *.stories.tsx)
        │   ├── MappingSheet.tsx   ← bottom-sheet (Radix Dialog) for manual mapping (receipt flow)
        │   ├── SupplierFormSheet.tsx  ← add/edit supplier form sheet (Settings UI)
        │   └── ProductPickerSheet.tsx ← reusable product-search picker (re-target a mapping)
        └── pages/             ← Login, Suppliers, Camera, ReceiptTable, Generate, Admin (Admin = «Налаштування» hub)
```

**Important structural facts that the code already depends on:**

- `backend/` is on `sys.path`, so imports are `apps.X` and `integrations.X`
  (never `valeraup.apps.X`). Each `apps/<x>/apps.py` declares
  `name="apps.<x>"` and `default_auto_field="django.db.models.BigAutoField"`.
- `integrations/` is a **plain Python package, not a Django app** — it is the
  single boundary to Gemini and SalesDrive. Keep external HTTP/SDK calls there.
- Migration files are **generated** (`makemigrations`), not hand-written, and **are
  committed** (`apps/<x>/migrations/0001_initial.py`). `entrypoint.sh` / the compose
  boot run `migrate` only — the schema is reproducible from the committed migrations,
  so no `makemigrations` is needed on deploy. When you change a model, run
  `makemigrations` and commit the new migration in the same PR.
- **Authorization is role-based** via `apps.accounts.permissions.IsAdmin` /
  `IsOperatorOrAdmin` (keyed on `Profile.role`), **not** Django's `IsAdminUser`
  (`is_staff`). A `post_save` signal (`apps.accounts.signals.ensure_profile`,
  wired in `AccountsConfig.ready()`) guarantees every user has exactly one
  `Profile(role='operator')`.

---

## 2. The golden rules (non-negotiable)

1. **Docstrings + type hints on everything.** Every Python module, class, and
   function has a Google-style docstring and full type hints. Every TS
   component/hook has TSDoc and typed props. No exceptions for "obvious" code.
2. **Explain WHY, not just what.** Comments and docstrings justify non-obvious
   decisions — especially SKU normalization, Gemini JSON parsing, the Excel
   column format, and cost math. The reader should never have to guess intent.
3. **Update `/docs` on every change.** A behavior change is not done until the
   relevant doc (`ARCHITECTURE.md`, `INTEGRATIONS.md`, `MAPPING.md`, `README.md`)
   reflects it. Docs that lie are worse than no docs.
4. **Structured JSON logging at key steps.** OCR request, mapping result, and
   Excel generation each emit a structured log event. See §6.
5. **Idempotency for anything re-runnable.** Celery tasks, catalog sync, and
   mapping writes must converge on re-run, not duplicate. See §7.
6. **Stay inside the manifest.** Do not invent models, fields, endpoints, or
   dependency versions beyond the agreed ТЗ. The manifest is a contract shared
   with parallel agents; drift breaks them.

---

## 3. Python conventions (mandatory for every `.py`)

These are already followed throughout `backend/` — match the existing style.

- **First line of every module:** `from __future__ import annotations`. This
  lets modern type hints (`X | None`, `list[dict]`) compile cleanly and keeps
  annotations lazy. Place it above all other imports.
- **Google-style docstrings** for module, class, and every function/method:
  one-line summary, then `Args:`, `Returns:`, and `Raises:` where applicable.
  Module docstrings explain the file's role and the key design decisions (look
  at `apps/mapping/services.py` and `integrations/gemini.py` for the bar).
- **Full type hints everywhere** — parameters and return types. Use built-in
  generics (`list[dict]`, `tuple[OurProduct | None, str]`).
- **Logger per module:** `logger = logging.getLogger(__name__)`. Never
  `print()`.
- **Keyword-only flags** where it aids clarity (e.g.
  `recognize_invoice(images, *, model=None)`).
- **Decimals, not floats**, for quantity (3 dp) and price/cost (2 dp). OCR
  numbers are coerced via a tolerant `_to_decimal` helper (comma → dot for
  Ukrainian invoices). Never introduce float rounding into money or quantities.

### Django patterns used here

- **Settings via `django-environ`.** All env-specific config flows through
  `env(...)` in `valeraup/settings.py`; a single `DATABASE_URL` drives the DB.
  Add new config as a typed env read with a safe default, and add the var to
  **both** `backend/.env.example` and `README.md`.
- **Services hold business logic, not views.** Views/serializers stay thin;
  real logic lives in `apps/<x>/services*.py` and `integrations/`. Example:
  `match_line` / `remember_mapping` (mapping), `build_receipt_xlsx` (receipts),
  `sync_catalog` (catalog). This keeps logic unit-testable without HTTP.
- **Tasks orchestrate, services compute.** A Celery task loads/saves models and
  calls services; the heavy lifting (parsing, matching, Excel) is in services so
  it can be tested synchronously.
- **`@shared_task` with an explicit `name=`** for tasks (see
  `recognize_receipt_task`) so routing is stable across imports.
- **DRF defaults are global:** `DEFAULT_AUTHENTICATION_CLASSES = SimpleJWT`,
  `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`,
  `DEFAULT_SCHEMA_CLASS = drf_spectacular.openapi.AutoSchema`. **Every non-auth
  endpoint requires authentication** — do not silently open one up. Use
  `@extend_schema` to keep the OpenAPI accurate where DRF can't infer it.
- **PINs and passwords are hashed** with Django's `make_password` /
  `check_password` (`Profile.pin_hash`). Never store or log a raw PIN. The caller
  sets their own PIN via `POST /api/auth/set-pin/` (authenticated).
- **`OurProduct.salesdrive_id` is the upsert key** for catalog sync;
  `ArticleMapping` is unique on `(supplier, supplier_sku_normalized)`. Respect
  those constraints rather than working around them.
- **`IntegrationSettings` is a DB singleton** (`apps/catalog/models.py`). It holds
  the admin-editable `salesdrive_yml_url`. `save()` pins `self.pk = 1`; read it via
  the `IntegrationSettings.load()` classmethod (`get_or_create(pk=1)`). The catalog
  YML URL is resolved in this order: explicit argument → `IntegrationSettings`
  (DB) → `settings.SALESDRIVE_YML_URL` (env fallback) — see `sync_catalog`. When
  you need config that an admin must change without a redeploy, extend this row
  rather than adding ad-hoc settings; the editing surface is the **Settings PWA**
  (`GET/PUT /api/settings/salesdrive/`), Django admin is secondary (add/delete
  disabled). `probe_catalog_yml(url)` is the **read-only** counterpart used by
  `POST /api/settings/salesdrive/test/` — it fetches + parses but never writes,
  and the test view always returns **HTTP 200** (a bad URL is a *result*, not a
  500), shaped `{ok, product_count, error}`.
- **Admin-editable directories are DRF `ModelViewSet`s + `DefaultRouter`, not
  Django admin.** Two such surfaces exist; both gate writes behind `IsAdmin` while
  keeping reads available where the operator flow needs them:
  - `SupplierViewSet` (`apps/suppliers`) → `GET/POST /api/suppliers/`,
    `GET/PUT/PATCH/DELETE /api/suppliers/{id}/`. `get_permissions()` grants
    `list`/`retrieve` to any authenticated user (operators pick a vendor) and
    requires `IsAdmin` for mutations. `list` returns active-only unless
    `?include_inactive=true`. `destroy()` catches `ProtectedError`
    (`Receipt.supplier=PROTECT`) and returns **409** with a "deactivate instead"
    message — never hard-delete a supplier with receipts; deactivate
    (`is_active=False`) to preserve the audit trail.
  - `ArticleMappingViewSet` (`apps/mapping`) → `GET/POST /api/mappings/`,
    `PATCH/DELETE /api/mappings/{id}/`, **all** `IsAdmin`. This is curation of the
    learned "memory", separate from the receipt-flow line-map action
    (`POST /api/receipts/{id}/lines/{id}/map/`, which calls `remember_mapping`).
    **The admin API must not bump `times_used`** (curation is not a "use"): it
    writes the normalized SKU via `update_or_create` on
    `(supplier, supplier_sku_normalized)` directly, and preserves `created_by` on
    re-target. `list` filters on `?supplier`/`?q`, `select_related`s supplier +
    product, orders by `-times_used`, and caps at 200.
- **Media goes through `default_storage`.** `ReceiptPhoto.image`
  (`ImageField(upload_to='receipts/%Y/%m/')`) saves the uploaded file via Django's
  default storage — Cloudflare R2 when the `R2_*` env vars are set, else
  `FileSystemStorage` under `MEDIA_ROOT`. `image_url` is mirrored from
  `image.url` for the frontend. The OCR task reads the bytes back server-side
  (`photo.image.open('rb')`), so it needs no public URL. Generated `.xlsx` is
  likewise written to `default_storage` (`receipts/xlsx/<id>.xlsx`). `Pillow` backs
  `ImageField`; `whitenoise` serves collected `/static/` in prod.

---

## 4. Frontend conventions

- **TSDoc on every component and hook**; typed props (no `any`). Components stay
  small and documented.
- **Mobile-first, touch-first.** Interactive targets ≥ 44px. This is a phone
  PWA used one-handed on a warehouse floor.
- **Design tokens, not hard-coded colors.** Use the CSS custom properties from
  `src/styles/tokens.css` (NextCRM navy `#0A1A3F` → electric blue `#2563EB` →
  cyan `#06B6D4`, Inter font). A comment marks that this file will be replaced by
  the real `@nextcrm/tokens` package later — do **not** add that package to
  `package.json` yet (it is private/unpublished).
- **Theming (light/dark).** `:root` holds the light tokens; `[data-theme='dark']`
  overrides the **same** variable names. `ThemeProvider` (`components/ThemeProvider.tsx`)
  sets `data-theme` on `<html>`, persists the choice in `localStorage`
  (`valeraup.theme`), and follows `prefers-color-scheme` until the user toggles
  via `ThemeToggle`. There are also `--surface-glass*` / `--glass-*` tokens for the
  "Liquid Glass 2026" `Card` surface. Read variables only — never hard-code colors
  — so a theme switch reskins the whole app.
- **UI kit** (`components/ui/`, each with TSDoc + typed props + a `*.stories.tsx`):
  `Button`, `Input`, `Card`, `Sheet` (Radix Dialog bottom-sheet), `Spinner`,
  `Skeleton`, `EmptyState`, `Toast`/`Toaster`/`useToast`, `StatusBadge`. 44px touch
  floor; WCAG contrast in both themes.
- **Accessibility:** status is never conveyed by color alone — `StatusBadge`
  pairs an icon + text with color (WCAG). Keep that pattern.
- **Auth token handling:** access token lives in memory; refresh token is noted
  for Capacitor Secure Storage. `src/lib/api.ts` is the single fetch wrapper
  (JWT attach + refresh), base URL from `import.meta.env.VITE_API_BASE_URL`. File
  uploads go through `api.postForm` / `receipts.uploadPhoto` as multipart
  `FormData` — **never** set a JSON `Content-Type` on those (the browser must add
  the multipart boundary).
- **Camera** (`lib/camera.ts`): `capturePhoto()` uses `@capacitor/camera` on native
  and a hidden `<input type="file" accept="image/*" capture="environment">` on web,
  returning a `File`.
- **Skeleton/empty/error states** are first-class — the pages render real
  `Skeleton` / `EmptyState` / error `Toast` states (e.g. `ReceiptTablePage` polls
  every ~2s while `recognizing` with a skeleton) rather than nothing on
  load/empty/failure.

---

## 5. The mapping core (read before touching it)

This is the heart of the product. Full detail in `docs/MAPPING.md`; the
implementation is `apps/mapping/services.py`.

- **`normalize_sku(raw)`** — trim, `UPPER()`, collapse internal whitespace runs
  to one space. It deliberately does **not** strip dashes/punctuation (`A-100`
  ≠ `A100`). The WHY: OCR adds cosmetic noise (case, doubled spaces) that must
  not create a second mapping, but punctuation is often a real part of the code.
- **`match_line(supplier_id, sku)`** is a **pure read** → `(OurProduct|None,
  "auto"|"unmapped")`. It does **not** mutate `times_used`; the caller bumps the
  counter only when a mapping is actually applied to a stored line (keeps the
  counter meaningful).
- **`remember_mapping(...)`** is **idempotent** on
  `(supplier, normalized sku)`: first manual map creates the row; later
  confirmations may re-target the product (operator correction) and always
  increment `times_used`, but never overwrite the original `created_by`.

If you change normalization rules, you must also update `docs/MAPPING.md` and
the cases in `backend/tests/test_mapping.py` — they are the behavioral contract.

---

## 6. Structured JSON logging

Logging is configured in `valeraup/settings.py` (`LOGGING`) using
`pythonjsonlogger.jsonlogger.JsonFormatter` on a `json` handler. App namespaces
(`apps`, `integrations`, `celery`) log at INFO; Django request noise is WARNING.

**Emit a structured event at each key pipeline step**, passing context via
`extra={...}` (never string-interpolate IDs into the message). Use a stable
snake_case event name as the message. The existing events to match and extend:

| Step                | Event name (message)        | Key `extra` fields                          |
|---------------------|-----------------------------|---------------------------------------------|
| OCR request         | `gemini_recognize_request`  | `model`, `image_count`                      |
| OCR result          | `gemini_recognize_result`   | `model`, `line_count`, `attempt`            |
| OCR parse failure   | `gemini_recognize_parse_error` / `gemini_recognize_failed` | `model`, `attempt`, `error` |
| Mapping auto-hit    | `mapping_match_auto`        | `supplier_id`, `normalized_sku`, `our_product_id` |
| Mapping miss        | `mapping_match_miss`        | `supplier_id`, `normalized_sku`             |
| Mapping learned     | `mapping_remembered`        | `supplier_id`, `our_product_id`, `times_used`, `was_created` |
| Excel built         | `receipt_xlsx_built`        | `receipt_id`, `rows_written`, `rows_skipped`, `bytes` |
| Recognize lifecycle | `receipt_recognize_*`       | `receipt_id`, `line_count`, `status`        |
| Photo uploaded      | `receipt_photo_uploaded`    | `receipt_id`, `photo_id`, `image_url`       |
| Status change       | `receipt_status_set` / `receipt_status_recomputed` | `receipt_id`, `previous_status`, `status` |
| Profile auto-create | `profile_auto_created`      | `user_id`, `role`                           |
| PIN set / login     | `pin_set` / `pin_login_*`   | `user_id` (**never** the PIN value)         |

**Never log secrets or raw PINs.** `raw_ocr_json` is stored on the line for
audit, but do not dump full image bytes into logs.

---

## 7. Idempotency (required for re-runnable work)

Celery can redeliver a task (worker crash/retry); imports can be re-triggered.
Every such path must converge, not compound:

- **`recognize_receipt_task`** deletes the receipt's existing lines inside a
  transaction before recreating them, so a re-run produces the same result. It
  also moves the receipt to `error` (not a hang) on any failure so the UI can
  offer retry, and uses an `F('times_used') + 1` expression to avoid
  read-modify-write races when lines share a mapping.
- **`sync_catalog`** upserts `OurProduct` by `salesdrive_id` (the natural key),
  so re-syncing updates in place rather than inserting duplicates.
- **`remember_mapping`** is `get_or_create` on the unique
  `(supplier, normalized)` pair inside `transaction.atomic()`.

When you add a new task or import, state in its docstring **how** it is
idempotent. If it can't be, say so loudly and explain why.

---

## 8. Receipt status machine

`Receipt.status` is the spine of the workflow. The two operations that move it
live in **`apps/receipts/services/status.py`** so the rule has one home:

- **`recompute_receipt_status(receipt)`** — derives the *data-driven* status from
  the current lines: no lines or any line lacking a `matched_product` →
  `needs_mapping`; every line matched → `ready`. It **never** auto-downgrades a
  terminal/explicit state (`xlsx_ready` / `error`). Called after every line
  `PATCH` and every `map/`, so `needs_mapping → ready` flips **automatically** the
  moment the last line is mapped (this is wired now, not a future TODO).
- **`set_receipt_status(receipt, status)`** — applies an *explicit* transition
  (e.g. a view flipping to `recognizing` or `xlsx_ready`), validating it against
  the allow-list and logging it; `error` is reachable from any state.

Valid transitions (see `docs/ARCHITECTURE.md` for the state diagram):

```
draft → recognizing → needs_mapping → ready → xlsx_ready
                    ↘ ready (if every line auto-matched)
   needs_mapping/ready ⇄ (re-recognise) → recognizing
   xlsx_ready → recognizing (re-open) ;  error → recognizing (retry)
   any step ───────────────────────────────────────────→ error
```

- `needs_mapping` whenever ≥1 line is `unmapped` (or nothing was recognized).
- `ready` only when every line has a `matched_product` (Excel can be generated).
- `error` on any task failure, so the UI shows retry instead of hanging.

Only `build_receipt_xlsx` exports lines that have a `matched_product`; it
defensively skips unmapped lines because they have no SalesDrive SKU to import
against.

---

## 9. The Excel / SalesDrive contract

There is **no direct SalesDrive write API** — the receipt is imported manually
via `Склад → Надходження → Імпорт`. `build_receipt_xlsx` produces exactly four
columns, centralized in `COLUMN_HEADERS` so the SalesDrive-template verification
is a one-line change:

| Column                | Source                          |
|-----------------------|---------------------------------|
| `SKU/Артикул`         | `matched_product.sku`           |
| `Назва`               | `matched_product.name`          |
| `Кількість`           | summed `line.quantity` (3 dp)   |
| `Ціна (собівартість)` | quantity-weighted avg price (2 dp) |

**Lines are grouped by `matched_product`** (skipping unmapped): duplicates of one
product are merged into a single row, **quantities summed**, and the price set to
the **quantity-weighted average** `Σ(qty·price) / Σ(qty)` so total receipt cost is
preserved through the merge (`_weighted_price`). This is the cost-preserving
default; the business may instead want *last* or *min* price — that is an **open
question (ТЗ §16)** flagged with a `TODO` in `services/xlsx.py`. If the rule
changes, update `_weighted_price`, `docs/INTEGRATIONS.md`, and `test_xlsx.py`
together.

**Before production, verify these headers/order against the live SalesDrive
import template** and update `docs/INTEGRATIONS.md`. The catalog itself comes
from the SalesDrive **YML export** (`shop → offers → offer`) parsed in
`integrations/salesdrive.py`.

---

## 10. Testing

Tests live in `backend/tests/` and run under `pytest` + `pytest-django`
(`pytest.ini` sets `DJANGO_SETTINGS_MODULE=valeraup.settings`). Tests describe
behavior and form the Definition of Done:

- `test_accounts.py` — profile auto-created on user create; `set-pin` then PIN
  login round-trips; `me` returns `{email, role, has_pin}`; `IsAdmin` blocks an
  operator on a protected view.
- `test_catalog.py` — parse a small sample YML string; sync upserts idempotently;
  product search by sku/name.
- `test_mapping.py` — `normalize_sku` cases (incl. Cyrillic), per-supplier
  isolation, operator correction, and auto-match after `remember_mapping`.
- `test_receipts.py` — create draft; `recompute_receipt_status` transitions; line
  `PATCH`; map flow sets `manual` + recompute.
- `test_upload.py` — photo upload creates a `ReceiptPhoto` with an `image`;
  recognize with `GEMINI_API_KEY` unset → lines empty, status sensible.
- `test_xlsx.py` — `build_receipt_xlsx` emits 4 columns; duplicate lines mapped to
  the same product → ONE row, summed quantity, weighted price.
- `test_models.py` — model creation, `unique_together`, `Receipt` status default.
- `test_api_smoke.py` — schema endpoint returns 200; `/api/suppliers/` returns
  401 without auth.

Conventions:

- Mark DB tests `@pytest.mark.django_db`.
- Use `factory-boy` for fixtures where helpful.
- **Mock the network boundary** (Gemini, SalesDrive HTTP) — never hit a live API
  in tests. `recognize_invoice` already short-circuits to `[]` when
  `GEMINI_API_KEY` is unset, which keeps CI offline-safe.
- A new behavior ships with a test that would fail without it.

Run locally:

```bash
cd backend && pytest
python manage.py check        # config sanity (also run in CI)
```

---

## 11. Definition of Done (the gate)

Work is **not done** until all four pass:

- [ ] **docs ✓** — `/docs` (and `README.md`) updated to match the change.
- [ ] **tests ✓** — new/changed behavior covered; `pytest` green.
- [ ] **OpenAPI ✓** — `/api/schema/` reflects reality (use `@extend_schema`
      where DRF can't infer it); `python manage.py check` clean.
- [ ] **standards ✓** — docstrings + type hints present, WHY explained,
      structured logging at key steps, idempotency stated where relevant.

CI (`.github/workflows/ci.yml`) enforces the mechanical half: backend runs
`manage.py check` + `pytest`; frontend runs `tsc -b` + `vite build`. Green CI is
necessary but not sufficient — the docs/standards half is on the author.

---

## 12. Pull requests — describe decisions and tradeoffs

Every PR description must explain **what changed, why, and what was traded off** —
not just a diff summary. Spell out:

- The decision made and the alternatives considered (e.g. "chose
  `get_or_create` over `update_or_create` because we must bump `times_used` with
  the current value and preserve original `created_by`").
- Any contract impact (models, endpoints, env vars, the Excel columns) — these
  affect parallel agents, so call them out explicitly.
- The DoD checklist (§11) with each box ticked and a one-line note of how.

Reviewers should be able to reconstruct your reasoning without reading your mind.

---

## 13. Hard "do nots"

- **Do not** invent models, fields, endpoints, or dependency versions beyond the
  manifest. It is a shared contract.
- **Do not** hand-write migration files in the skeleton (use `makemigrations`).
- **Do not** put external HTTP/SDK calls anywhere but `integrations/`.
- **Do not** log secrets, raw PINs, or full image bytes.
- **Do not** open a non-auth endpoint without an explicit, justified reason.
- **Do not** add `@nextcrm/tokens` to `package.json` (unpublished) — use
  `src/styles/tokens.css`. The only frontend dependency added beyond the skeleton
  is `@radix-ui/react-dialog` (powers the `Sheet` / `MappingSheet` primitive).
- **Do not** use floats for money or quantities — `Decimal` only.
- **Do not** delete the DB or media volumes on redeploy — `docker compose build`
  + `up`, never `down -v`. The dev worker embeds Celery beat (`-B`); production
  (`docker-compose.prod.yml`) runs beat as its **own** `beat` service so the
  schedule has a single owner.
- **Do not** edit the dev `docker-compose.yml` for prod changes — prod has its own
  `docker-compose.prod.yml`.

---

*This guide describes the code as it actually exists. When you change the code,
change this guide and `/docs` in the same PR — keeping them honest is part of the
Definition of Done.*
