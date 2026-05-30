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
