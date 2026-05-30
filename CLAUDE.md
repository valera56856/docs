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
├── docker-compose.yml         ← 5 services: db, redis, backend, worker, frontend
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
│   ├── requirements.txt       ← pinned deps (incl. dev/test under a comment)
│   ├── pytest.ini             ← DJANGO_SETTINGS_MODULE=valeraup.settings
│   ├── conftest.py            ← shared pytest fixtures
│   ├── Dockerfile             ← python:3.12-slim
│   ├── .env.example           ← safe placeholders, never real keys
│   ├── valeraup/              ← project package
│   │   ├── settings.py  urls.py  celery.py  __init__.py (imports celery_app)
│   │   └── wsgi.py  asgi.py
│   ├── integrations/          ← external boundaries (NOT Django apps)
│   │   ├── gemini.py          ← recognize_invoice(), SYSTEM_PROMPT
│   │   └── salesdrive.py      ← fetch_catalog_yml(), parse_catalog_yml()
│   ├── apps/                  ← the 5 domain apps (AppConfig.name = "apps.<x>")
│   │   ├── accounts/          ← Profile (role, pin_hash); auth views (login/refresh/pin)
│   │   ├── suppliers/         ← Supplier
│   │   ├── catalog/           ← OurProduct + services.sync_catalog + tasks
│   │   ├── mapping/           ← ArticleMapping + services (normalize/match/remember)
│   │   └── receipts/          ← Receipt/ReceiptPhoto/ReceiptLine + services/xlsx + tasks
│   └── tests/                 ← test_mapping, test_xlsx, test_models, test_api_smoke
│
└── frontend/                  ← React 19 + Vite + TS PWA + Capacitor + Storybook
    ├── package.json  vite.config.ts  tsconfig*.json  capacitor.config.ts
    ├── index.html  nginx.conf  Dockerfile  .env.example
    ├── public/                ← manifest.webmanifest, robots.txt, icons/
    ├── .storybook/            ← main.ts, preview.ts (imports tokens.css)
    └── src/
        ├── main.tsx  App.tsx  router.tsx  vite-env.d.ts
        ├── styles/            ← tokens.css (NextCRM palette), global.css
        ├── lib/               ← cn.ts, api.ts (JWT fetch), auth.tsx (AuthProvider)
        ├── types/index.ts     ← mirrors backend models
        ├── components/        ← ui/Button, ui/StatusBadge, MappingSheet
        └── pages/             ← Login, Suppliers, Camera, ReceiptTable, Generate, Admin
```

**Important structural facts that the code already depends on:**

- `backend/` is on `sys.path`, so imports are `apps.X` and `integrations.X`
  (never `valeraup.apps.X`). Each `apps/<x>/apps.py` declares
  `name="apps.<x>"` and `default_auto_field="django.db.models.BigAutoField"`.
- `integrations/` is a **plain Python package, not a Django app** — it is the
  single boundary to Gemini and SalesDrive. Keep external HTTP/SDK calls there.
- Migration files are **generated** (`makemigrations`), not hand-written. Only
  `migrations/__init__.py` is committed in the skeleton.

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
  `check_password` (`Profile.pin_hash`). Never store or log a raw PIN.
- **`OurProduct.salesdrive_id` is the upsert key** for catalog sync;
  `ArticleMapping` is unique on `(supplier, supplier_sku_normalized)`. Respect
  those constraints rather than working around them.

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
- **Accessibility:** status is never conveyed by color alone — `StatusBadge`
  pairs an icon + text with color (WCAG). Keep that pattern.
- **Auth token handling:** access token lives in memory; refresh token is noted
  for Capacitor Secure Storage. `src/lib/api.ts` is the single fetch wrapper
  (JWT attach + refresh), base URL from `import.meta.env.VITE_API_BASE_URL`.
- **Skeleton/empty/error states** are first-class — page stubs already note
  them; fill them in rather than rendering nothing on load/empty/failure.

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
| Mapping learned     | `mapping_remembered`        | `supplier_id`, `our_product_id`, `times_used`, `created` |
| Excel built         | `receipt_xlsx_built`        | `receipt_id`, `rows_written`, `rows_skipped`, `bytes` |
| Recognize lifecycle | `receipt_recognize_*`       | `receipt_id`, `line_count`, `status`        |

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

`Receipt.status` is the spine of the workflow. Valid transitions
(see `docs/ARCHITECTURE.md` for the state diagram):

```
draft → recognizing → needs_mapping → ready → xlsx_ready
                    ↘ ready (if every line auto-matched)
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
| `SKU/Артикул`         | `line.matched_product.sku`      |
| `Назва`               | `line.matched_product.name`     |
| `Кількість`           | `line.quantity` (3 dp)          |
| `Ціна (собівартість)` | `line.price` (purchase cost, 2 dp) |

**Before production, verify these headers/order against the live SalesDrive
import template** and update `docs/INTEGRATIONS.md`. The catalog itself comes
from the SalesDrive **YML export** (`shop → offers → offer`) parsed in
`integrations/salesdrive.py`.

---

## 10. Testing

Tests live in `backend/tests/` and run under `pytest` + `pytest-django`
(`pytest.ini` sets `DJANGO_SETTINGS_MODULE=valeraup.settings`). Tests describe
behavior and form the Definition of Done:

- `test_mapping.py` — `normalize_sku` cases + auto-match after
  `remember_mapping`.
- `test_xlsx.py` — `build_receipt_xlsx` emits the 4 columns with correct values.
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
  `src/styles/tokens.css`.
- **Do not** use floats for money or quantities — `Decimal` only.
- **Do not** delete the DB or media volumes on redeploy — `docker compose build`
  + `up`, never `down -v`. (Worker embeds Celery beat for dev only; split it in
  production.)

---

*This guide describes the code as it actually exists. When you change the code,
change this guide and `/docs` in the same PR — keeping them honest is part of the
Definition of Done.*
