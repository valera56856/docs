/**
 * Typed `fetch` wrapper for the Valeraup REST API.
 *
 * Responsibilities:
 * - Prefix every request with `VITE_API_BASE_URL`.
 * - Attach the in-memory JWT access token as a Bearer header.
 * - On a `401`, transparently attempt a single token refresh (via a callback
 *   the AuthProvider registers) and replay the original request once.
 * - Surface non-2xx responses as a typed {@link ApiError}.
 *
 * WHY the access token lives in module memory (not localStorage): keeping it out
 * of persistent web storage limits XSS token theft. The long-lived refresh token
 * is stored by the AuthProvider in Capacitor Secure Storage on device.
 */
import type {
  CatalogSyncResult,
  GenerateXlsxResult,
  LinePatch,
  MappingAdmin,
  Me,
  OurProduct,
  PhotoUploadResult,
  Receipt,
  RecognizeResult,
  SalesDriveSettings,
  SalesDriveTestResult,
  Supplier,
  SupplierInput,
  TokenPair,
} from '@/types';

/** Base URL including the trailing `/api`, from the build-time env. */
const BASE_URL = import.meta.env.VITE_API_BASE_URL;

/** The current access token, held only in memory. */
let accessToken: string | null = null;

/**
 * Optional refresh hook the AuthProvider registers. When a request gets a 401,
 * the wrapper calls this to obtain a fresh access token, then retries once.
 * Returns the new access token, or null if refresh failed (forcing re-login).
 */
let refreshHandler: (() => Promise<string | null>) | null = null;

/** Set (or clear with `null`) the in-memory access token used for requests. */
export function setAccessToken(token: string | null): void {
  accessToken = token;
}

/** Read the current in-memory access token (mainly for tests / debugging). */
export function getAccessToken(): string | null {
  return accessToken;
}

/**
 * Register the refresh callback. The AuthProvider owns refresh-token storage,
 * so it provides the actual refresh logic; the wrapper just triggers it.
 */
export function setRefreshHandler(
  handler: (() => Promise<string | null>) | null,
): void {
  refreshHandler = handler;
}

/** Error thrown for any non-2xx API response, carrying status + parsed body. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API request failed with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

/** Options accepted by {@link request}; mirrors a subset of RequestInit. */
export interface RequestOptions extends Omit<RequestInit, 'body'> {
  /** JSON-serializable request body (set automatically with the JSON header). */
  json?: unknown;
  /**
   * Multipart body (file uploads). When set, we send it as-is and deliberately
   * do NOT set a `Content-Type` header — the browser must add the
   * `multipart/form-data` boundary itself, so forcing JSON here would corrupt
   * the request. Mutually exclusive with {@link json}.
   */
  form?: FormData;
  /** When false, do not attach the Authorization header (e.g. login). */
  auth?: boolean;
}

/**
 * Build headers for a request, attaching JSON + Bearer auth as appropriate.
 *
 * @param options - The caller's request options.
 * @returns A populated Headers instance.
 */
function buildHeaders(options: RequestOptions): Headers {
  const headers = new Headers(options.headers);
  // Only set a JSON content-type for JSON bodies. For `form` (multipart) we must
  // leave Content-Type unset so the browser appends the correct boundary.
  if (
    options.json !== undefined &&
    options.form === undefined &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json');
  }
  if (options.auth !== false && accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }
  return headers;
}

/**
 * Perform a single HTTP request to the API (no retry logic).
 *
 * @typeParam T - Expected shape of the parsed JSON response.
 * @param path - Path relative to the API base, e.g. `/suppliers/`.
 * @param options - Request options (method, json body, auth toggle, ...).
 * @returns The parsed response body, or `undefined` for 204 No Content.
 * @throws {@link ApiError} for any non-2xx response.
 */
async function rawRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { json, form, auth, ...rest } = options;
  // Body precedence: multipart `form` (sent verbatim) > JSON > raw RequestInit
  // body. Exactly one of `form` / `json` is expected per call.
  const body: BodyInit | undefined =
    form !== undefined
      ? form
      : json !== undefined
        ? JSON.stringify(json)
        : undefined;
  const response = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: buildHeaders(options),
    body,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  // Some endpoints (e.g. xlsx generation) may return non-JSON; guard parsing.
  const contentType = response.headers.get('Content-Type') ?? '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new ApiError(response.status, payload);
  }
  return payload as T;
}

/**
 * Perform an authenticated request with one transparent refresh-and-retry on a
 * 401 response.
 *
 * @typeParam T - Expected shape of the parsed JSON response.
 * @param path - Path relative to the API base.
 * @param options - Request options.
 * @returns The parsed response body.
 * @throws {@link ApiError} if the request fails (after a refresh attempt).
 */
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  try {
    return await rawRequest<T>(path, options);
  } catch (error) {
    const canRetry =
      error instanceof ApiError &&
      error.status === 401 &&
      options.auth !== false &&
      refreshHandler !== null;

    if (!canRetry) {
      throw error;
    }

    const newToken = await refreshHandler!();
    if (!newToken) {
      throw error;
    }
    // Replay the original request once with the refreshed token.
    return rawRequest<T>(path, options);
  }
}

/** Convenience verb helpers built on {@link request}. */
export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', json }),
  patch: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', json }),
  put: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PUT', json }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
  /**
   * POST a multipart `FormData` body (file uploads). Goes through the same
   * refresh-and-retry pipeline as every other call; the Content-Type boundary
   * is left for the browser to set (see {@link RequestOptions.form}).
   */
  postForm: <T>(path: string, form: FormData, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', form }),
};

/**
 * Low-level auth calls used by the AuthProvider. Kept here so all network access
 * funnels through the one wrapper (consistent error handling + base URL).
 */
export const authApi = {
  /** Exchange email + password for a JWT pair. */
  login: (email: string, password: string) =>
    api.post<TokenPair>('/auth/login/', { email, password }, { auth: false }),

  /** Fast login by 4-digit PIN (the backend identifies the profile by email). */
  pin: (email: string, pin: string) =>
    api.post<TokenPair>('/auth/pin/', { email, pin }, { auth: false }),

  /** Exchange a refresh token for a new access token. */
  refresh: (refresh: string) =>
    api.post<{ access: string }>(
      '/auth/refresh/',
      { refresh },
      { auth: false },
    ),

  /** Fetch the current user summary ({email, role, has_pin}). */
  me: () => api.get<Me>('/auth/me/'),

  /**
   * Set (or replace) the caller's 4-digit PIN so future logins can use the fast
   * PIN flow. Returns nothing (the backend responds 204).
   *
   * @param pin - Exactly four digits. Never logged or persisted in plaintext.
   */
  setPin: (pin: string) => api.post<void>('/auth/set-pin/', { pin }),
};

/**
 * Domain API — typed, named calls for the receipt workflow.
 *
 * Each group maps one-to-one onto the backend contract. Centralizing the paths
 * here keeps pages declarative (they call `receipts.uploadPhoto(id, file)`
 * rather than hand-building URLs) and gives one place to evolve the contract.
 */

/** Supplier reads + admin CRUD (the receipt-flow entry point and admin mgmt). */
export const suppliers = {
  /**
   * List suppliers, ordered by name.
   *
   * By default only **active** suppliers are returned (the operator picker
   * relies on this). Pass `{ includeInactive: true }` from the admin screen to
   * also see deactivated suppliers (the backend honours `?include_inactive=true`).
   *
   * @param options - Optional flags. `includeInactive` widens the result set.
   */
  list: (options?: { includeInactive?: boolean }) =>
    api.get<Supplier[]>(
      options?.includeInactive ? '/suppliers/?include_inactive=true' : '/suppliers/',
    ),

  /**
   * Create a supplier (admin only; 403 otherwise).
   *
   * @param data - The writable supplier fields.
   */
  create: (data: SupplierInput) => api.post<Supplier>('/suppliers/', data),

  /**
   * Partially update a supplier (admin only). Used both for edits and for the
   * "deactivate" action (`{ is_active: false }`).
   *
   * @param id - Supplier id.
   * @param data - The subset of fields to change.
   */
  update: (id: number, data: Partial<SupplierInput>) =>
    api.patch<Supplier>(`/suppliers/${id}/`, data),

  /**
   * Delete a supplier (admin only). The backend returns **409** when the
   * supplier still has linked receipts (ProtectedError) — callers should catch
   * that and suggest deactivation instead.
   *
   * @param id - Supplier id.
   */
  remove: (id: number) => api.delete<void>(`/suppliers/${id}/`),
};

/** Catalog product reads + admin sync trigger. */
export const products = {
  /**
   * Search the catalog by SKU or name for the mapping dropdown.
   *
   * @param q - Free-text query. A blank query yields an empty list server-side.
   */
  search: (q: string) =>
    api.get<OurProduct[]>(`/products/search/?q=${encodeURIComponent(q)}`),
};

/** Catalog admin operations. */
export const catalog = {
  /** Enqueue a SalesDrive catalog sync (admin only; 403 otherwise). */
  sync: () => api.post<CatalogSyncResult>('/sync/catalog/'),
};

/**
 * DB-configurable SalesDrive integration settings (admin only).
 *
 * The YML URL the catalog sync pulls from now lives in the database (with the
 * `SALESDRIVE_YML_URL` env var as a fallback), so an admin can repoint it from
 * the UI and validate it before syncing.
 */
export const settings = {
  /** Read the current SalesDrive settings + catalog cache summary. */
  getSalesDrive: () => api.get<SalesDriveSettings>('/settings/salesdrive/'),

  /**
   * Persist a new SalesDrive YML URL. Returns the updated read shape.
   *
   * @param url - The SalesDrive YML export URL (may be blank to clear it).
   */
  saveSalesDrive: (url: string) =>
    api.put<SalesDriveSettings>('/settings/salesdrive/', {
      salesdrive_yml_url: url,
    }),

  /**
   * Probe a SalesDrive YML URL without persisting it. The endpoint never
   * throws on a bad URL — it returns `{ ok: false, error }` with HTTP 200 — so
   * the caller reads the result rather than catching.
   *
   * @param url - Optional URL to test; when omitted the saved URL is probed.
   */
  testSalesDrive: (url?: string) =>
    api.post<SalesDriveTestResult>(
      '/settings/salesdrive/test/',
      url !== undefined ? { salesdrive_yml_url: url } : {},
    ),
};

/** Remembered article mappings (admin management). */
export const mappings = {
  /**
   * List remembered mappings (admin only), most-used first (server caps at 200).
   *
   * @param options - Optional filters. `supplier` scopes to one supplier id;
   *   `q` free-text-matches the supplier SKU or our product's SKU/name.
   */
  list: (options?: { supplier?: number; q?: string }) => {
    const params = new URLSearchParams();
    if (options?.supplier !== undefined) {
      params.set('supplier', String(options.supplier));
    }
    if (options?.q) {
      params.set('q', options.q);
    }
    const qs = params.toString();
    return api.get<MappingAdmin[]>(`/mappings/${qs ? `?${qs}` : ''}`);
  },

  /**
   * Create (or re-target, by unique supplier+normalized-SKU) a mapping.
   *
   * @param data - The supplier id, the raw supplier SKU, and the target product.
   */
  create: (data: {
    supplier: number;
    supplier_sku: string;
    our_product_id: number;
  }) => api.post<MappingAdmin>('/mappings/', data),

  /**
   * Re-target an existing mapping to a different product (the "Перепривʼязати"
   * action). Returns the updated read shape.
   *
   * @param id - Mapping id.
   * @param data - The new product id.
   */
  update: (id: number, data: { our_product_id: number }) =>
    api.patch<MappingAdmin>(`/mappings/${id}/`, data),

  /**
   * Forget a mapping (admin only).
   *
   * @param id - Mapping id.
   */
  remove: (id: number) => api.delete<void>(`/mappings/${id}/`),
};

/** Receipt lifecycle calls. */
export const receipts = {
  /**
   * Create a draft receipt for a supplier.
   *
   * @param supplierId - The chosen supplier's id.
   */
  create: (supplierId: number) =>
    api.post<Receipt>('/receipts/', { supplier: supplierId }),

  /** Fetch a receipt with its nested photos + lines. */
  get: (id: number) => api.get<Receipt>(`/receipts/${id}/`),

  /**
   * Upload one invoice-page photo as multipart. The backend stores the file and
   * returns its id + URL.
   *
   * @param id - Receipt id.
   * @param file - The captured image as a {@link File} (web) or Blob-as-File.
   */
  uploadPhoto: (id: number, file: File) => {
    const form = new FormData();
    form.append('image', file, file.name || 'photo.jpg');
    return api.postForm<PhotoUploadResult>(`/receipts/${id}/photos/`, form);
  },

  /** Enqueue Gemini OCR for the receipt's uploaded photos. */
  recognize: (id: number) =>
    api.post<RecognizeResult>(`/receipts/${id}/recognize/`),

  /** Build + store the Excel receipt; returns its download URL. */
  generateXlsx: (id: number) =>
    api.post<GenerateXlsxResult>(`/receipts/${id}/generate-xlsx/`),
};

/** Receipt-line edits + mapping. */
export const lines = {
  /**
   * Partially edit a line (quantity / price / recognized sku/name). Returns the
   * fully serialized updated line.
   *
   * @param receiptId - Owning receipt id.
   * @param lineId - Line id.
   * @param patch - The subset of fields to change.
   */
  patch: (receiptId: number, lineId: number, patch: LinePatch) =>
    api.patch<Receipt['lines'][number]>(
      `/receipts/${receiptId}/lines/${lineId}/`,
      patch,
    ),

  /**
   * Map a line to one of our products. The backend remembers the mapping
   * (so the supplier SKU auto-matches next time) and returns the updated line.
   *
   * @param receiptId - Owning receipt id.
   * @param lineId - Line id.
   * @param ourProductId - The chosen catalog product's id.
   */
  map: (receiptId: number, lineId: number, ourProductId: number) =>
    api.post<Receipt['lines'][number]>(
      `/receipts/${receiptId}/lines/${lineId}/map/`,
      { our_product_id: ourProductId },
    ),
};
