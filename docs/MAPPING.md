# MAPPING — the SKU-mapping core

This is the heart of Valeraup. A supplier prints its own article codes
(`supplier_sku`) on the invoice; SalesDrive knows our products by *our* SKUs.
Mapping is the translation layer that turns a recognized supplier SKU into one of
our catalog products — **automatically** once it has been taught, **manually**
the first time, and it **remembers** every manual decision so it never has to ask
twice.

> Map once, remember forever.

The entire mechanism lives in three small, pure-ish functions in
[`apps/mapping/services.py`](../backend/apps/mapping/services.py) plus one model,
[`ArticleMapping`](../backend/apps/mapping/models.py). This document is precise
about what each one does, because every other part of the receipt pipeline
depends on it behaving exactly as described.

---

## 1. Where mapping sits in the pipeline

```
photo → Gemini OCR → ReceiptLine(recognized_sku) → match_line() ─┬─ auto  → matched_product set, status="auto"
                                                                 └─ miss  → status="unmapped"  → operator picks product
                                                                                                       │
                                                                                  remember_mapping() ──┘  (status="manual")
```

* **OCR → lines.** `apps.receipts.tasks.recognize_receipt_task` creates one
  `ReceiptLine` per recognized item and immediately calls `match_line()` for each.
* **Auto path.** If a remembered `ArticleMapping` exists, the line is resolved
  with `match_status="auto"` and the mapping's `times_used` is incremented.
* **Manual path.** If no mapping exists, the line is stored `match_status="unmapped"`.
  The operator selects the correct product in the UI; the
  `POST /api/receipts/{id}/lines/{line_id}/map/` endpoint
  (`apps.receipts.views.ReceiptLineMapView`) calls `remember_mapping()`, sets the
  line to `match_status="manual"`, and the mapping now exists for next time.

The receipt's status is driven directly by mapping results:

* every line matched (auto or already manual) → `Receipt.status = "ready"`;
* any line still `unmapped` → `Receipt.status = "needs_mapping"`.

---

## 2. Normalization — `normalize_sku(raw: str) -> str`

Source: [`apps/mapping/services.py`](../backend/apps/mapping/services.py).

A SKU read off a photo is noisy. The same real article arrives as `"abc 123 "`,
`"ABC  123"`, or `"ABC 123"` depending on OCR spacing and case. If we keyed
mappings on the raw string, each cosmetic variant would create a **separate**
mapping, defeating the whole "remember it" promise and tripping the operator into
re-mapping the same product repeatedly.

`normalize_sku` produces a single canonical key:

| Rule | What it does | Why |
| --- | --- | --- |
| **Trim** | strip leading/trailing whitespace | OCR and copy/paste add meaningless edge spaces |
| **Collapse internal whitespace** | every run of spaces/tabs → one single space | `"ABC  123"` must equal `"ABC 123"` |
| **Uppercase** | fold to upper case | supplier codes are case-insensitive in practice; `abc-1` ≡ `ABC-1` |

Implementation is intentionally tiny and total:

```python
def normalize_sku(raw: str) -> str:
    if not raw:
        return ""
    # str.split() with no args splits on any run of whitespace and drops empty
    # tokens, so join-with-single-space trims the ends AND collapses internal
    # runs in one pass.
    return " ".join(raw.split()).upper()
```

### What normalization deliberately does **not** do

* **It does not strip punctuation or dashes.** `A-100` and `A100` are treated as
  *different* SKUs. Dashes, dots and slashes are frequently meaningful parts of a
  supplier's code, and merging them risks pointing two genuinely different
  products at one mapping — a silent, expensive error in a warehouse receipt.
* **It does not transliterate or fuzzy-match.** Normalization is exact after
  canonicalization. There is no Levenshtein/edit-distance step; a one-character
  OCR misread is an `unmapped` line the operator fixes, not a wrong auto-match.
* **Empty in → empty out.** Falsy/whitespace-only input returns `""`. The lookup
  layer treats an empty normalized SKU as an automatic miss (see below).

### Normalization examples

| Raw `supplier_sku` | `normalize_sku` result |
| --- | --- |
| `"abc 123"` | `"ABC 123"` |
| `"  ABC  123 "` | `"ABC 123"` |
| `"ABC123"` | `"ABC123"` |
| `"a-100"` | `"A-100"` |
| `"А-100"` (Cyrillic А) | `"А-100"` (NOT the same as Latin `A-100`) |
| `""` / `"   "` | `""` |

> **Cyrillic vs Latin caveat.** Uppercasing does not unify visually-identical
> Cyrillic and Latin letters (`А` U+0410 vs `A` U+0041). They normalize to
> different keys and therefore different mappings. This is correct behaviour —
> we must not guess the operator's intent — but worth knowing when an
> "obviously the same" SKU stubbornly stays `unmapped`.

---

## 3. Lookup — `match_line(supplier_id, supplier_sku) -> (OurProduct | None, str)`

```python
def match_line(supplier_id: int, supplier_sku: str) -> tuple[OurProduct | None, str]:
    ...
```

`match_line` answers one question: *do we already know what this supplier SKU
maps to?* It is a **pure read** — it never writes. (The `times_used` counter is
bumped by the **caller** only when a mapping is actually applied to a stored line,
so the count reflects real usage; see §6.)

Algorithm:

1. `normalized = normalize_sku(supplier_sku)`.
2. If `normalized` is empty → return `(None, "unmapped")` and log
   `mapping_match_empty_sku`.
3. Look up `ArticleMapping` filtered by `(supplier_id, supplier_sku_normalized=normalized)`,
   `select_related("our_product")`, take the first.
4. **Hit** → return `(mapping.our_product, "auto")`, log `mapping_match_auto`.
5. **Miss** → return `(None, "unmapped")`, log `mapping_match_miss`.

### Scope: mappings are per-supplier

The lookup key is the pair **`(supplier_id, normalized SKU)`** — never the SKU
alone. Two different suppliers can legitimately reuse the same code `"100"` for
completely different products, so a mapping learned for Supplier A is invisible to
Supplier B. This is enforced structurally by the unique constraint (§5) and by the
`supplier_id` filter in every query.

### The two outcomes `match_line` can return

| Returned status | Meaning | `our_product` |
| --- | --- | --- |
| `"auto"` | a remembered mapping resolved the SKU | the mapped `OurProduct` |
| `"unmapped"` | no mapping exists (or empty SKU) | `None` |

`match_line` **never** returns `"manual"`. `"manual"` is a *line* state, set by
the map endpoint after an operator picks a product (§4). The full enum on
`ReceiptLine.match_status` is `auto` / `manual` / `unmapped`, but only `auto` and
`unmapped` originate from `match_line`.

---

## 4. Manual mapping + learning — `remember_mapping(...)`

```python
def remember_mapping(
    supplier_id: int,
    supplier_sku: str,
    our_product_id: int,
    created_by: str = "",
) -> ArticleMapping:
    ...
```

Called by `ReceiptLineMapView` when the operator picks a product for an `unmapped`
(or to-be-corrected) line. It persists the decision so the *next* receipt from the
same supplier auto-matches that SKU.

Behaviour, step by step:

1. `normalized = normalize_sku(supplier_sku)`.
2. Inside a single `transaction.atomic()`:
   * `get_or_create` on `(supplier_id, supplier_sku_normalized=normalized)`.
     * **Created** → store `supplier_sku` (raw, for audit/display),
       `our_product_id`, `created_by`, `times_used=0`.
     * **Existing** → re-point `our_product_id` (operator correction) and refresh
       the raw `supplier_sku`; **never** overwrite the original `created_by`.
   * `times_used += 1` — every confirmation counts as a use and strengthens the
     mapping.
   * `save(update_fields=["our_product", "supplier_sku", "times_used"])`.
3. Log `mapping_remembered` (with `created` flag and new `times_used`).

Then the view sets the line: `matched_product = product`,
`match_status = "manual"`.

### Idempotency & corrections

`remember_mapping` is **idempotent on `(supplier, normalized sku)`**:

* Mapping the **same** line to the **same** product twice does not create a
  duplicate row — it bumps `times_used` and re-saves.
* Mapping the same SKU to a **different** product (operator fixing a mistake)
  re-targets the existing row in place. There is always exactly one mapping per
  `(supplier, normalized SKU)`; the latest manual decision wins.
* The unique constraint is the safety net: even under a race, the database refuses
  a second row for the same key.

### `created_by` semantics

`created_by` records the **original** author of the mapping and is written only on
first creation. Subsequent corrections by another operator do not rewrite it. The
field is plain text (username/email), blank for system-created entries.

---

## 5. The model & its invariants — `ArticleMapping`

Source: [`apps/mapping/models.py`](../backend/apps/mapping/models.py).

| Field | Type | Notes |
| --- | --- | --- |
| `supplier` | FK → `suppliers.Supplier`, `CASCADE` | deleting a supplier removes its mappings |
| `supplier_sku` | `CharField(255)` | raw SKU as printed/recognized — audit & display only |
| `supplier_sku_normalized` | `CharField(255)`, `db_index=True` | the lookup key; produced by `normalize_sku` |
| `our_product` | FK → `catalog.OurProduct`, `CASCADE` | the product the SKU resolves to |
| `times_used` | `PositiveIntegerField(default=0)` | learning signal; how often this mapping has been used/confirmed |
| `created_by` | `CharField(255, blank=True)` | original author |
| `created_at` | `DateTimeField(auto_now_add=True)` | first-stored timestamp |

Class constants `MATCH_AUTO = "auto"` and `MATCH_MANUAL = "manual"` name the
statuses used across the pipeline.

**Key invariant — the unique constraint:**

```python
class Meta:
    unique_together = ("supplier", "supplier_sku_normalized")
```

This is *the* guarantee that makes the system trustworthy: **at most one mapping
per supplier per normalized SKU.** Cosmetic spelling variants collapse onto one
key (because they normalize identically), so they cannot produce competing,
conflicting mappings. The `db_index` on `supplier_sku_normalized` keeps the
per-line auto-match query fast even with a large mapping table.

> Note on the `CASCADE` from `our_product`: if a product is deleted from the
> catalog, its mappings are deleted too — a mapping pointing at a non-existent
> product is meaningless. The *receipt line*, by contrast, uses `SET_NULL`
> (`matched_product` becomes `NULL`), so historical receipts survive a catalog
> change; the line simply needs re-mapping.

---

## 6. The `times_used` learning counter — exact semantics

`times_used` is the system's lightweight "what do we rely on most" signal. It is
incremented in **two distinct places**, and the distinction matters:

1. **Auto-match application** — in `apps.receipts.tasks.recognize_receipt_task`.
   When a line auto-matches, the task issues a DB-level
   `update(times_used=F("times_used") + 1)` on the matched mapping. The
   `F`-expression increment is deliberate: it avoids a read-modify-write race when
   several lines in the same OCR run share one mapping.

2. **Manual confirmation** — inside `remember_mapping`, every call bumps
   `times_used` by one (including the first creation, which goes `0 → 1`).

`match_line` itself does **not** touch `times_used` — it is a pure read. This
keeps the counter meaningful: it counts *applications* of a mapping to real lines,
not idle lookups.

Today the counter is a usage/audit signal (surfaced in Django admin and the
mapping read serializer). It is the natural ranking key for any future
"suggest the most-used product" UX.

---

## 7. Status vocabulary — don't confuse the three enums

Three different `match`-flavoured vocabularies coexist; keeping them straight
avoids bugs:

| Where | Values | Set by |
| --- | --- | --- |
| `match_line()` return | `auto`, `unmapped` | the lookup itself |
| `ReceiptLine.match_status` | `auto`, `manual`, `unmapped` | OCR task (`auto`/`unmapped`) and map endpoint (`manual`) |
| `ArticleMapping.MATCH_*` constants | `auto`, `manual` | module-level names used in code |

A line is `auto` only when `match_line` resolved it from a remembered mapping; it
becomes `manual` only after an operator explicitly maps it; it stays `unmapped`
until one of those happens.

---

## 8. Edge cases (and exactly how the system handles them)

### 8.1 Formatting variance / OCR noise
Handled by `normalize_sku`. Whitespace and case differences collapse to one key,
so `"ABC 123"` learned today auto-matches `" abc  123 "` read tomorrow. Dash/
punctuation differences (`A-100` vs `A100`) are **not** collapsed and remain
distinct mappings by design.

### 8.2 Duplicate lines on one invoice → sum the quantity
The same product can appear on multiple physical lines of one invoice (e.g. two
boxes listed separately). Each becomes its own `ReceiptLine`, and each auto-matches
to the **same** `OurProduct` independently (and each bumps `times_used`). The
mapping layer does not merge them — that is correct, because the lines may carry
different prices. **Summation happens downstream, at Excel build time:** lines
sharing the same matched product should be aggregated (quantities summed) so
SalesDrive receives one receipt row per product. See
[`apps/receipts/services/xlsx.py`](../backend/apps/receipts/services/xlsx.py) and
[INTEGRATIONS.md](INTEGRATIONS.md) (weighted-average cost note) for the cost
treatment when prices differ across the duplicate lines.

> Rule of thumb: **mapping never de-duplicates; aggregation is the Excel step's
> job.** Mapping's only promise is "same SKU → same product."

### 8.3 Product missing from our catalog
If the supplier's item simply isn't in our SalesDrive catalog yet, no mapping can
be created — there is nothing to point at. The line stays `unmapped` and the
receipt stays `needs_mapping`; the operator cannot proceed to a clean Excel for
that line. Resolution paths:

1. Run **catalog sync** (`POST /api/sync/catalog/`) to pull a freshly-added
   product from the SalesDrive YML, then re-open the mapping sheet and map it.
2. If the product truly does not exist in SalesDrive, it must be created there
   first; Valeraup intentionally does not invent catalog entries.

Until then the operator can edit quantity/price on the line, but mapping is
blocked by the absence of a target product.

### 8.4 Empty or unreadable SKU
OCR may return a blank `supplier_sku` (`null` per the Gemini prompt). `normalize_sku`
yields `""`, `match_line` short-circuits to `unmapped` (logging
`mapping_match_empty_sku`), and the operator maps the line by hand using the
recognized name as the cue. The blank SKU can still be stored, but it is a poor
key; mapping such a line is allowed but will only auto-match other equally-blank
lines, so operators are encouraged to correct the SKU first via the line PATCH
endpoint.

### 8.5 Operator corrects a previous mapping
Re-mapping a SKU to a different product re-points the single existing
`ArticleMapping` (latest decision wins) and bumps `times_used`. Already-stored
lines on *other* receipts are **not** retroactively changed — only future
auto-matches use the corrected target. This avoids silently rewriting history.

### 8.6 Two suppliers, same code
Not a collision. Mappings are keyed on `(supplier, normalized SKU)`, so
Supplier A's `"100"` and Supplier B's `"100"` are independent rows resolving to
independent products. See §3 (Scope).

### 8.7 Re-running OCR on a receipt (idempotency)
The recognize task deletes existing lines before recreating them, so a redelivered
Celery task converges rather than duplicating. Auto-match runs again on the fresh
lines, so a mapping created between runs will now resolve a previously-`unmapped`
line.

---

## 9. Structured logging reference

Every mapping decision emits a JSON log line (logger name
`apps.mapping.services`), so the auto/manual flow is fully auditable:

| Event | Emitted by | Key fields |
| --- | --- | --- |
| `mapping_match_empty_sku` | `match_line` | `supplier_id` |
| `mapping_match_miss` | `match_line` | `supplier_id`, `normalized_sku` |
| `mapping_match_auto` | `match_line` | `supplier_id`, `normalized_sku`, `our_product_id`, `mapping_id` |
| `mapping_remembered` | `remember_mapping` | `supplier_id`, `normalized_sku`, `our_product_id`, `mapping_id`, `created`, `times_used` |

The receipt-side counterparts (`receipt_recognize_start/done/error`,
`receipt_line_mapped`) live in the receipts app and tie each mapping decision back
to a specific receipt and line.

---

## 10. Quick reference

| Function | Signature | Pure read? | Writes `times_used`? |
| --- | --- | --- | --- |
| `normalize_sku` | `(raw: str) -> str` | yes | no |
| `match_line` | `(supplier_id, supplier_sku) -> (OurProduct \| None, str)` | yes | no (caller does) |
| `remember_mapping` | `(supplier_id, supplier_sku, our_product_id, created_by="") -> ArticleMapping` | no | yes (`+1` per call) |

| Endpoint | Effect on mapping |
| --- | --- |
| `POST /api/receipts/{id}/recognize/` | creates lines, runs `match_line` per line, bumps `times_used` on auto hits |
| `POST /api/receipts/{id}/lines/{line_id}/map/` | calls `remember_mapping`, sets line `match_status="manual"` |
| `GET /api/products/search/?q=` | feeds the operator's manual product picker |
| `POST /api/sync/catalog/` | refreshes the catalog so missing products become mappable |

See also: [ARCHITECTURE.md](ARCHITECTURE.md) (system data flow & Receipt state
machine) and [INTEGRATIONS.md](INTEGRATIONS.md) (SalesDrive YML parsing and the
4-column Excel receipt).
