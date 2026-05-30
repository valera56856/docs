# Integrations

Valeraup has exactly two external integrations:

1. **SalesDrive** — the source of our product catalog (read) and the destination
   for purchase receipts (write, via a manually imported `.xlsx` file).
2. **Google Gemini 2.5 Flash Vision** — OCR that turns photographed supplier
   invoices into structured line items.

Both integrations are isolated behind the `backend/integrations/` package so the
rest of the app never talks to a third party directly. This document is the
single reference for how those boundaries work and — crucially — which parts must
be **verified against the live SalesDrive UI before production use**.

| Code | Purpose |
| --- | --- |
| [`backend/integrations/salesdrive.py`](../backend/integrations/salesdrive.py) | Fetch + parse SalesDrive YML catalog |
| [`backend/apps/catalog/services.py`](../backend/apps/catalog/services.py) | Upsert parsed offers into `OurProduct` (`sync_catalog`); read-only probe (`probe_catalog_yml`) |
| [`backend/apps/catalog/models.py`](../backend/apps/catalog/models.py) | `IntegrationSettings` singleton (DB-stored YML URL) |
| [`backend/apps/catalog/views.py`](../backend/apps/catalog/views.py) | Admin Settings API: `GET/PUT /api/settings/salesdrive/`, `POST .../test/`, `POST /api/sync/catalog/` |
| [`backend/apps/catalog/management/commands/sync_catalog.py`](../backend/apps/catalog/management/commands/sync_catalog.py) | CLI catalog sync (`manage.py sync_catalog`) |
| [`backend/apps/receipts/services/xlsx.py`](../backend/apps/receipts/services/xlsx.py) | Build the receipt `.xlsx` for SalesDrive import (group + weighted price) |
| [`backend/integrations/gemini.py`](../backend/integrations/gemini.py) | Gemini Vision OCR of invoice photos (real `google-genai` call) |

---

## 1. SalesDrive

SalesDrive is the ERP/CRM of record. Valeraup interacts with it in **two
directions**, neither of which uses a direct REST API:

- **Catalog in (read):** SalesDrive exports the full product catalog as a YML
  "shop" file (the Yandex Market XML dialect). Valeraup downloads and mirrors it.
- **Receipt out (write):** Valeraup generates an `.xlsx` file that a manager
  **manually** imports into SalesDrive. There is intentionally no programmatic
  write path — see [§1.5](#15-receipt-import-manual-step).

### 1.1 YML catalog export

The catalog URL is **configured in the database** (admin-editable through the
designed Settings PWA) with the `SALESDRIVE_YML_URL` env var as a deploy-time
**fallback**. To obtain the URL in the SalesDrive admin:

> **Установки → Товари/Послуги → Експорт YML**

That screen produces a stable, fully-qualified URL to a generated YML file.

**Where the URL lives now.** It is stored on the `IntegrationSettings` singleton
(`apps.catalog.models.IntegrationSettings`, see [§1.4](#14-db-configurable-yml-url-the-settings-api)),
edited via `PUT /api/settings/salesdrive/`. The env var remains as a fallback for
fresh deploys before the row is set:

```dotenv
# Optional fallback; the DB value (set in the Settings UI) takes precedence.
SALESDRIVE_YML_URL=https://example.salesdrive.ua/export/yml/
```

**Resolution order** (in `sync_catalog`, highest priority first):

1. the explicit `yml_url` argument (a one-off override / test),
2. `IntegrationSettings.load().salesdrive_yml_url` (set in the Settings UI),
3. `settings.SALESDRIVE_YML_URL` (env fallback).

`sync_catalog` raises `ValueError` only when **all three** are blank.

**Fetch.** `integrations.salesdrive.fetch_catalog_yml(yml_url)` performs a plain
`requests.get` with a split timeout — a short connect timeout to fail fast on a
dead host, and a generous read timeout because the export can be large:

```python
_HTTP_TIMEOUT: tuple[int, int] = (10, 120)  # (connect, read) seconds
```

It raises `ValueError` if the URL is empty and propagates
`requests.HTTPError` / `requests.RequestException` on transport failures, and
logs `salesdrive_fetch_request` / `salesdrive_fetch_result` (with byte count).

### 1.2 YML structure and parsing

The YML follows the standard shop structure. Valeraup only cares about the
offers:

```xml
<yml_catalog date="2026-05-30 12:00">
  <shop>
    <name>Our Shop</name>
    <offers>
      <offer id="12345" available="true">
        <name>Гель-лак Kodi 8ml, рожевий</name>
        <vendorCode>KODI-8-PINK</vendorCode>
        <price>180</price>
        <param name="Артикул">KODI-8-PINK</param>
      </offer>
      ...
    </offers>
  </shop>
</yml_catalog>
```

`integrations.salesdrive.parse_catalog_yml(yml_bytes)` walks
`yml_catalog → shop → offers → offer` (using a tolerant `.//offer` search so it
works regardless of wrapper depth) and returns a list of plain dicts:

```python
[{"salesdrive_id": "12345", "sku": "KODI-8-PINK", "name": "Гель-лак Kodi 8ml, рожевий"}, ...]
```

**Keying.** Each offer's `id` attribute becomes `salesdrive_id` — SalesDrive's
stable identifier, which is `unique` on `OurProduct`. Offers **without** an `id`
are skipped (an offer we cannot deterministically key on is useless as an upsert
target) and counted in the `skipped` log field.

**SKU resolution.** SalesDrive has no single canonical SKU tag across exports, so
`_offer_sku()` looks in priority order and uses the **first non-empty** value:

1. `<vendorCode>`
2. `<article>`
3. `<param name="Артикул">` / `name="SKU"` / `name="vendorCode"` (case-insensitive)
4. the `offer` `id` attribute (last-resort fallback)

> **VERIFY before production:** confirm which of these tags your specific
> SalesDrive export actually populates with the SKU that matches what suppliers
> print on their invoices. The mapping logic ([docs/MAPPING.md](./MAPPING.md))
> joins on this `sku`, so picking the wrong tag silently breaks auto-matching.

**Errors.** `parse_catalog_yml` raises `ValueError` if the bytes are not
well-formed XML, or if there are no `<offer>` elements at all. Parsing uses the
stdlib `xml.etree.ElementTree`, which does **not** resolve external entities by
default — sufficient hardening for a trusted account export.

### 1.3 Upsert into the local cache

`integrations.salesdrive` stays free of Django ORM concerns. The upsert lives in
`apps.catalog.services.sync_catalog(yml_url)`:

- Resolves the URL in priority order — explicit argument →
  `IntegrationSettings.salesdrive_yml_url` (DB) → `settings.SALESDRIVE_YML_URL`
  (env) — and raises `ValueError` only when all three are blank (see
  [§1.1](#11-yml-catalog-export)).
- Wraps all writes in a single `transaction.atomic()` so a sync that fails
  halfway never leaves the cache torn / half-updated.
- Upserts each offer with `OurProduct.objects.update_or_create(salesdrive_id=…)`
  — **idempotent**: a re-sync updates `sku`/`name` in place instead of creating
  duplicates. Running it repeatedly converges the cache to whatever the YML
  currently contains.
- Returns the number of products synced and logs `catalog_sync_start` /
  `catalog_sync_done` (with `synced` / `created` / `updated` counts).

It is invoked from four places without duplicating logic:

```mermaid
flowchart LR
    A["POST /api/sync/catalog/<br/>(admin: IsAdmin)"] --> S
    B["Celery beat<br/>(daily 03:00)"] --> S
    D["manage.py sync_catalog<br/>(CLI / cron)"] --> S
    C["tests"] --> S
    S["sync_catalog(yml_url)"] --> F["fetch_catalog_yml"]
    F --> P["parse_catalog_yml"]
    P --> U["update_or_create<br/>OurProduct (by salesdrive_id)"]
```

The API endpoint and the Celery beat go through the async `sync_catalog_task`
(`apps.catalog.tasks`); the CLI command and tests call `sync_catalog` directly
(synchronously). All four converge on the same idempotent upsert. The admin
«Синхронізувати» button in the Settings PWA simply hits `POST /api/sync/catalog/`
(the first arm above).

### 1.4 DB-configurable YML URL: the Settings API

The YML URL and a small catalog-status summary are managed from the designed
**Settings PWA** (`/admin` → «Налаштування») instead of Django admin or a
redeploy. Three admin-only endpoints back that screen (all
`IsAuthenticated` + `apps.accounts.permissions.IsAdmin` — the product `admin`
role on `Profile`, **not** Django's `is_staff`), implemented in
`apps.catalog.views`:

| Method & path | View | Behaviour |
| --- | --- | --- |
| `GET /api/settings/salesdrive/` | `SalesDriveSettingsView.get` | Returns `{salesdrive_yml_url, last_synced, product_count}`. |
| `PUT /api/settings/salesdrive/` | `SalesDriveSettingsView.put` | Saves `{salesdrive_yml_url}` onto the singleton; returns the **same** read shape so the UI re-renders without a follow-up `GET`. A blank URL is valid — it clears the value and re-arms the env fallback. |
| `POST /api/settings/salesdrive/test/` | `SalesDriveTestView.post` | Probes a URL (body `{salesdrive_yml_url}` if present, else the stored one) and returns `{ok, product_count, error}`. |

**The read shape** (`SalesDriveSettingsReadSerializer`) bundles the stored config
with two derived figures so the screen renders in one round-trip:

- `salesdrive_yml_url` — the stored value (`IntegrationSettings.load()`),
- `last_synced` — `OurProduct.objects.aggregate(Max("last_synced"))`, or `null`
  if the catalog has never been synced,
- `product_count` — `OurProduct.objects.count()`.

**The singleton.** `IntegrationSettings` (`apps.catalog.models`) is a one-row
config table: `save()` pins `self.pk = 1` and `load()` is a `get_or_create(pk=1)`
classmethod, so there is exactly one config row no matter how many times it is
instantiated. The WHY: a redeploy-free, durable home for the URL without inventing
a key/value store. It is also registered in Django admin (add disabled once the
row exists, delete disabled — clear the URL instead) as a secondary inspection
view; the **primary** editing surface is the PWA.

**Test connection always returns HTTP 200.** `probe_catalog_yml(yml_url)`
(`apps.catalog.services`) runs the same `fetch_catalog_yml` + `parse_catalog_yml`
boundary calls as a sync but performs **no** database write, returning
`{"product_count": n}`. It deliberately lets exceptions propagate; the view
catches **any** exception (bad URL, unreachable host, malformed YML, or an empty
URL anywhere) and converts it into `{"ok": false, "product_count": null, "error":
str(exc)}` with **HTTP 200**. The WHY: a failed connectivity test is an expected
*result*, not a server fault — returning 200 lets the UI show a friendly inline
message instead of a generic 5xx. A successful probe returns `{"ok": true,
"product_count": n, "error": null}`. It logs `salesdrive_settings_test_ok` /
`salesdrive_settings_test_failed` (the error string never contains secrets);
`PUT` logs `salesdrive_settings_saved` with a `has_url` boolean (the URL itself is
not logged).

> Probing **never mutates the cache** — only `sync_catalog` writes. So an admin
> can validate a URL, then click «Зберегти» and «Синхронізувати» to commit it.

### 1.5 Receipt import (manual step)

There is **no direct API write** to SalesDrive. The manager imports the generated
`.xlsx` by hand:

> **Склад → Надходження → Імпорт**

This is a deliberate product decision: SalesDrive's receipt import gives the
manager a final human review of cost and quantity before stock and weighted-
average cost are mutated. Valeraup's job ends at producing a correct file.

#### The four-column format

`apps.receipts.services.xlsx.build_receipt_xlsx(receipt)` produces a single-sheet
workbook (sheet title `Надходження`) with a header row plus **one row per distinct
matched product**:

| Column header (`COLUMN_HEADERS`) | Source field |
| --- | --- |
| `SKU/Артикул` | `matched_product.sku` |
| `Назва` | `matched_product.name` |
| `Кількість` | summed `line.quantity` (Decimal, 3 dp) |
| `Ціна (собівартість)` | quantity-weighted avg price (Decimal, 2 dp) |

Implementation notes:

- **Lines are grouped by `matched_product`.** OCR can split one catalog product
  across several invoice lines (a multi-page invoice, the same article listed
  twice), and two different supplier SKUs can map to the same `OurProduct`.
  SalesDrive's importer expects one row per product, so duplicates are merged: the
  group's quantities are **summed**, and the price is the **quantity-weighted
  average** `Σ(qty·price) / Σ(qty)` (`_weighted_price`), which preserves the total
  receipt cost `Σ qty·price` exactly through the merge. Rows appear in first-seen
  order (dict insertion order) for a predictable, reviewable file.

  > **OPEN QUESTION (ТЗ §16):** the business may instead prefer *last* price (most
  > recent purchase) or *min* price (most conservative cost). Quantity-weighted
  > average is the cost-preserving default. If the SalesDrive workflow dictates
  > otherwise, change `_weighted_price` and update this doc + `test_xlsx.py`
  > together (the `# TODO(ТЗ §16)` in `xlsx.py` marks the spot).

  Edge cases in `_weighted_price`: a group whose total quantity is 0 falls back to
  the plain mean of the available prices; a group where OCR read **no** price
  leaves the cell blank (`None`) for the operator to fill in SalesDrive.

- **Only matched lines are written.** A line with no `matched_product` has no
  SalesDrive SKU to import against, so it is skipped and counted in `rows_skipped`.
  In normal flow this never triggers, because the receipt only reaches `ready`
  once every line is mapped — the skip is defensive.
- `Decimal` values are written **as-is** (the merged quantity/price are quantized
  to 3 dp / 2 dp); openpyxl serializes them to exact numeric cells with no float
  rounding.
- The function logs `receipt_xlsx_built` with `rows_written`, `rows_skipped` and
  byte size. It returns `bytes`, written to `default_storage` at
  `receipts/xlsx/<id>.xlsx` (R2 in prod, filesystem in dev) by
  `ReceiptGenerateXlsxView`, which then records `xlsx_url` and flips the receipt to
  `xlsx_ready`.

> **VERIFY before production:** the exact header strings, their order, the sheet
> title, and whether SalesDrive's importer expects an inclusive-of-VAT or
> net cost in the price column **must be checked against the live SalesDrive
> import template**. All of these are centralized as the module constants
> `SHEET_TITLE` and `COLUMN_HEADERS`, so adjusting them is a one-line change.

#### Weighted-average cost example

SalesDrive maintains stock cost as a **weighted average**. The `Ціна
(собівартість)` we send is the per-unit **purchase price** of this receipt's
goods; SalesDrive blends it with existing stock on import. Worked example:

- Existing stock: **10 units** at an average cost of **₴100** → inventory value
  **₴1 000**.
- This receipt (our `.xlsx`): **5 units** at **₴130** → added value **₴650**.
- After import:
  - total units = 10 + 5 = **15**
  - total value = 1 000 + 650 = **₴1 650**
  - new weighted-average cost = 1 650 / 15 = **₴110.00**

So Valeraup is responsible only for reporting the **honest purchase price and
quantity per SKU**; SalesDrive does the averaging. This is why the `price` column
is the *cost* of the goods in this delivery, not a sale price.

---

## 2. Gemini 2.5 Flash Vision (OCR)

`integrations.gemini` is the single boundary between Valeraup and Google's Gemini
API. It sends one or more photographed pages of **a single supplier invoice** to
the `gemini-2.5-flash` model (via the `google-genai` SDK) and returns structured
line-item dicts.

Configuration:

```dotenv
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-2.5-flash
```

### 2.1 System prompt

The agreed prompt (`gemini.SYSTEM_PROMPT`, in Ukrainian) is intentionally terse
and imperative — the model follows short, unambiguous output-shape instructions
far more reliably than long descriptive ones. It instructs the model to:

- Extract **all** product line items across the supplied page(s).
- Return **only** a valid JSON array of objects — no prose, no Markdown, nothing
  before or after the array.
- Use **exactly** these four fields per object (the contract consumed by
  `recognize_receipt_task`):

  | Field | Meaning | Type |
  | --- | --- | --- |
  | `supplier_sku` | supplier's article / product code | string |
  | `name` | product name | string |
  | `quantity` | quantity | number |
  | `price` | unit price / cost | number |

- Put `null` for any value not present on the invoice (so downstream code can
  tell "OCR could not read it" apart from "value is 0").
- **Never invent** values not visible on the photo.
- Return an empty array `[]` if there are no line items.

### 2.2 JSON response handling: fence-strip + retry

LLMs frequently wrap JSON in Markdown code fences even when told not to. Parsing
must never depend on the model obeying the prompt, so the response is handled
defensively:

```mermaid
flowchart TD
    A["recognize_invoice(images)"] --> K{"GEMINI_API_KEY set?<br/>images non-empty?"}
    K -- "no" --> Z["log skip → return []"]
    K -- "yes" --> C["_call_gemini → raw text"]
    C --> S["_strip_code_fences<br/>(remove ```json … ```)"]
    S --> P["json.loads + assert list"]
    P -- "ok" --> R["return list of dicts"]
    P -- "JSONDecodeError / ValueError" --> RT{"attempt < 2?"}
    RT -- "yes (retry once)" --> C
    RT -- "no" --> E["raise ValueError<br/>(unparseable after retry)"]
```

Step by step (`recognize_invoice(images, *, model=None)`):

1. **Skip guards.** If `images` is empty, or `settings.GEMINI_API_KEY` is unset
   (local/dev/CI without a key), it logs `gemini_recognize_skip` and returns `[]`
   — the pipeline and test suite run with no network access or secrets.
2. **Call.** `_call_gemini()` makes the **real `google-genai` call**: it imports
   the SDK **lazily** (`from google import genai` / `from google.genai import
   types`) so the module never fails to import when the package is absent, builds
   `client = genai.Client(api_key=settings.GEMINI_API_KEY)`, assembles a multimodal
   request — the `SYSTEM_PROMPT` followed by each page as
   `types.Part.from_bytes(data=img, mime_type="image/jpeg")` — and calls
   `client.models.generate_content(model=settings.GEMINI_MODEL, contents=parts)`,
   returning `response.text`. It raises `RuntimeError` if the `google-genai` SDK is
   not installed.
3. **Fence strip.** `_strip_code_fences()` removes a leading/trailing
   ```` ```json ``` ```` (or bare ```` ``` ````) fence and trims whitespace.
4. **Parse.** `json.loads`, then assert the result is a `list`; non-dict
   elements are filtered out so one stray element cannot poison the batch.
5. **Retry once.** On `JSONDecodeError` / `ValueError`, the call is retried
   **exactly once** (two attempts total) — transient LLM JSON glitches usually
   recover on a re-ask, and capping at one retry bounds cost and latency.
6. **Give up cleanly.** If both attempts fail, it logs `gemini_recognize_failed`
   and raises `ValueError("Gemini returned an unparseable response after one
   retry")`.

A successful response looks like:

```json
[
  {"supplier_sku": "ABC-123", "name": "Гель-лак рожевий 8ml", "quantity": 12, "price": 95.50},
  {"supplier_sku": "ABC-777", "name": "Базове покриття 15ml", "quantity": 3,  "price": null}
]
```

### 2.3 Structured logging and `raw_ocr_json` audit

Every key step emits a structured JSON log line via `logging.getLogger(__name__)`,
so OCR cost and quality can be audited off-host:

| Event | When |
| --- | --- |
| `gemini_recognize_skip` | no images / no API key |
| `gemini_recognize_request` | request sent (model, image count) |
| `gemini_recognize_result` | success (line count, attempt number) |
| `gemini_recognize_parse_error` | a parse attempt failed |
| `gemini_recognize_failed` | both attempts failed |

In addition, the **per-line raw model output is persisted** for audit. The
`ReceiptLine.raw_ocr_json` `JSONField` stores what Gemini returned for that line.
This is the audit trail that lets an operator answer *"why did the system read it
this way?"* — when a quantity or price looks wrong, the original recognized dict
is right there next to the (possibly human-edited) `quantity` / `price` columns,
without having to re-run OCR or dig through logs.

### 2.4 How OCR fits the receipt pipeline

`recognize_invoice` is called from the Celery task
`apps.receipts.tasks.recognize_receipt_task`, which:

1. loads the receipt's photo **bytes** back from `default_storage` server-side
   (`photo.image.open('rb')` — no public URL needed, so a private R2 bucket
   works; unreadable/URL-only photos are skipped with a warning),
2. calls `gemini.recognize_invoice(images)` (returns `[]` when the API key is
   unset or there are no images — offline-safe),
3. deletes any prior lines (idempotency) and creates `ReceiptLine` rows inside a
   transaction (storing each raw dict in `raw_ocr_json`; quantity/price parsed
   with a comma→dot tolerant `_to_decimal`),
4. runs `apps.mapping.services.match_line` per line (see
   [docs/MAPPING.md](./MAPPING.md)) and bumps `times_used` on auto-matches,
5. transitions `Receipt.status` via `recompute_receipt_status`
   (`recognizing → needs_mapping` / `ready`), or `error` on any failure.

See [docs/ARCHITECTURE.md](./ARCHITECTURE.md) for the full
photo → OCR → mapping → Excel → SalesDrive flow and the receipt state diagram.
