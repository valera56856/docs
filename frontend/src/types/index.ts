/**
 * Shared domain types — the frontend mirror of the Django/DRF models.
 *
 * Keep these in lock-step with the backend models (apps/suppliers, apps/catalog,
 * apps/mapping, apps/receipts). Field names match the serialized API payloads.
 */

/** Status of a single recognized receipt line's mapping to our catalog. */
export type MatchStatus = 'auto' | 'manual' | 'unmapped';

/** Lifecycle status of a {@link Receipt}. Mirrors Receipt.STATUS on the backend. */
export type ReceiptStatus =
  | 'draft'
  | 'recognizing'
  | 'needs_mapping'
  | 'ready'
  | 'xlsx_ready'
  | 'error';

/** A supplier whose invoices we recognize. Mirrors suppliers.Supplier. */
export interface Supplier {
  id: number;
  name: string;
  note: string;
  is_active: boolean;
  created_at: string;
}

/**
 * A product from our SalesDrive catalog cache. Mirrors catalog.OurProduct.
 * `sku` is what ends up in the generated Excel receipt.
 */
export interface OurProduct {
  id: number;
  salesdrive_id: string;
  sku: string;
  name: string;
  last_synced: string;
}

/**
 * A single line on a recognized invoice. Mirrors receipts.ReceiptLine.
 *
 * `quantity` / `price` arrive as strings because DRF serializes DecimalField as
 * a string to preserve precision (cost math must not lose cents).
 */
export interface ReceiptLine {
  id: number;
  receipt: number;
  recognized_sku: string;
  recognized_name: string;
  quantity: string;
  price: string | null;
  matched_product: OurProduct | null;
  match_status: MatchStatus;
}

/** A photographed invoice attached to a receipt. Mirrors receipts.ReceiptPhoto. */
export interface ReceiptPhoto {
  id: number;
  receipt: number;
  image_url: string;
}

/** A receipt (a recognized invoice) with its lines. Mirrors receipts.Receipt. */
export interface Receipt {
  id: number;
  supplier: number;
  status: ReceiptStatus;
  xlsx_url: string;
  created_by: string;
  created_at: string;
  photos: ReceiptPhoto[];
  lines: ReceiptLine[];
}

/** JWT token pair returned by the auth endpoints. */
export interface TokenPair {
  access: string;
  refresh: string;
}

/** Product role of a user, mirrors `Profile.role` on the backend. */
export type UserRole = 'admin' | 'operator';

/**
 * Current-user summary from `GET /api/auth/me/`.
 *
 * Drives the admin gate (only `admin` may open `/admin`) and the "set PIN"
 * affordance (offered when `has_pin` is false).
 */
export interface Me {
  email: string;
  role: UserRole;
  has_pin: boolean;
}

/** A remembered supplier-SKU → product mapping. Mirrors mapping.ArticleMapping. */
export interface ArticleMapping {
  id: number;
  supplier: number;
  supplier_sku: string;
  supplier_sku_normalized: string;
  our_product: OurProduct | null;
  times_used: number;
  created_by: string;
  created_at: string;
}

/**
 * Result of `POST /api/receipts/{id}/photos/` (multipart upload).
 *
 * The backend saves the file to default storage and echoes the stored URL so the
 * client can render a thumbnail immediately, without a receipt refetch.
 */
export interface PhotoUploadResult {
  id: number;
  image_url: string;
}

/** Result of `POST /api/receipts/{id}/recognize/` — the enqueue acknowledgement. */
export interface RecognizeResult {
  task_id: string;
  status: ReceiptStatus;
}

/** Result of `POST /api/receipts/{id}/generate-xlsx/`. */
export interface GenerateXlsxResult {
  xlsx_url: string;
  status: ReceiptStatus;
}

/** Result of `POST /api/sync/catalog/` — the admin catalog-sync enqueue. */
export interface CatalogSyncResult {
  task_id: string;
  detail: string;
}

/** Partial-edit payload for `PATCH /api/receipts/{id}/lines/{lineId}/`. */
export interface LinePatch {
  /** Decimal string (3 dp) to preserve precision end-to-end. */
  quantity?: string;
  /** Decimal string (2 dp) purchase cost, or null to clear. */
  price?: string | null;
  /** Corrected supplier SKU as recognized from the invoice. */
  recognized_sku?: string;
  /** Corrected product name as recognized from the invoice. */
  recognized_name?: string;
}
