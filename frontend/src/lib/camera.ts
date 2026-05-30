/**
 * camera — capture a photo of a printed invoice, returning a {@link File}.
 *
 * Dual path (documented because the two branches behave subtly differently):
 *
 * - **Native (Capacitor)**: when `Capacitor.isNativePlatform()` is true we use
 *   `@capacitor/camera`'s `Camera.getPhoto`, which opens the OS camera UI and
 *   returns the image as a base64 data URL. We decode that into a `File` so the
 *   rest of the app (upload, preview) treats native and web captures identically.
 *
 * - **Web fallback**: in a browser there is no Capacitor camera, so we inject a
 *   hidden `<input type="file" accept="image/*" capture="environment">`. On a
 *   phone browser this still opens the rear camera; on desktop it opens a file
 *   picker. The native `change`/`cancel` events resolve or reject the promise.
 *
 * Both branches converge on a single return type — `Promise<File>` — so callers
 * never branch on platform. A user cancellation rejects with a {@link
 * CameraCancelledError} the caller can ignore (it is not a real error).
 *
 * The Capacitor modules are imported **dynamically** so the web bundle does not
 * eagerly pull native plugin code, and so unit tests / Storybook (which have no
 * Capacitor runtime) can import this module without it throwing at load time.
 */

/** Thrown (rejected) when the user dismisses the camera/picker without a photo. */
export class CameraCancelledError extends Error {
  constructor(message = 'Захоплення фото скасовано.') {
    super(message);
    this.name = 'CameraCancelledError';
  }
}

/** Options for {@link capturePhoto}. */
export interface CapturePhotoOptions {
  /**
   * JPEG quality 0–100 for the native path (ignored on web, where the camera
   * app / OS controls quality). Defaults to 80 — a good balance of OCR
   * legibility versus upload size on a warehouse connection.
   */
  quality?: number;
}

/**
 * Decode a base64 data URL (`data:image/jpeg;base64,...`) into a {@link File}.
 *
 * WHY synchronous decode instead of `fetch(dataUrl).then(r => r.blob())`: it
 * avoids an extra network-shaped round-trip and works in WebViews where
 * `fetch` of a `data:` URL is occasionally restricted.
 *
 * @param dataUrl - The `data:` URL returned by the native camera.
 * @param filename - Name to assign the resulting file.
 * @returns A {@link File} with the decoded bytes and a best-effort MIME type.
 */
function dataUrlToFile(dataUrl: string, filename: string): File {
  const [header, base64 = ''] = dataUrl.split(',');
  const mimeMatch = /data:(.*?);base64/.exec(header);
  const mime = mimeMatch?.[1] ?? 'image/jpeg';
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new File([bytes], filename, { type: mime });
}

/**
 * Capture a photo on the native (Capacitor) path.
 *
 * @param quality - JPEG quality 0–100.
 * @returns The captured image as a {@link File}.
 * @throws {@link CameraCancelledError} when the user cancels the camera.
 */
async function captureNative(quality: number): Promise<File> {
  // Dynamic import keeps native plugin code out of the web bundle.
  const { Camera, CameraResultType, CameraSource } = await import(
    '@capacitor/camera'
  );
  try {
    const photo = await Camera.getPhoto({
      quality,
      // DataUrl so we can build a File without touching the filesystem layer.
      resultType: CameraResultType.DataUrl,
      source: CameraSource.Camera,
      // Skip the system "edit photo" step — operators want the raw page.
      allowEditing: false,
    });
    if (!photo.dataUrl) {
      throw new CameraCancelledError();
    }
    const ext = photo.format ? `.${photo.format}` : '.jpg';
    return dataUrlToFile(photo.dataUrl, `invoice-${Date.now()}${ext}`);
  } catch (error) {
    // Capacitor throws a generic Error with a "cancel"-ish message on dismiss.
    const message = error instanceof Error ? error.message.toLowerCase() : '';
    if (message.includes('cancel')) {
      throw new CameraCancelledError();
    }
    throw error;
  }
}

/**
 * Capture a photo on the web path via a transient hidden file input.
 *
 * @returns The selected/captured image as a {@link File}.
 * @throws {@link CameraCancelledError} when the picker is dismissed.
 */
function captureWeb(): Promise<File> {
  return new Promise<File>((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    // `capture` hints mobile browsers to open the rear camera directly.
    input.setAttribute('capture', 'environment');
    input.style.display = 'none';

    let settled = false;
    const cleanup = (): void => {
      input.remove();
    };

    input.addEventListener(
      'change',
      () => {
        settled = true;
        const file = input.files?.[0];
        cleanup();
        if (file) {
          resolve(file);
        } else {
          reject(new CameraCancelledError());
        }
      },
      { once: true },
    );

    // Browsers fire `cancel` (where supported) when the picker is dismissed.
    input.addEventListener(
      'cancel',
      () => {
        if (!settled) {
          cleanup();
          reject(new CameraCancelledError());
        }
      },
      { once: true },
    );

    document.body.appendChild(input);
    input.click();
  });
}

/**
 * Capture a single invoice photo, choosing the best path for the runtime.
 *
 * @param options - {@link CapturePhotoOptions}.
 * @returns A {@link File} ready to upload via `receipts.uploadPhoto`.
 * @throws {@link CameraCancelledError} if the user cancels.
 * @example
 * try {
 *   const file = await capturePhoto();
 *   await receipts.uploadPhoto(receiptId, file);
 * } catch (e) {
 *   if (!(e instanceof CameraCancelledError)) toast({ variant: 'error', ... });
 * }
 */
export async function capturePhoto(
  options: CapturePhotoOptions = {},
): Promise<File> {
  const { quality = 80 } = options;

  // Resolve the platform lazily so the web bundle stays light and tests/Storybook
  // (no Capacitor) fall through to the web path cleanly.
  let isNative = false;
  try {
    const { Capacitor } = await import('@capacitor/core');
    isNative = Capacitor.isNativePlatform();
  } catch {
    // No Capacitor runtime (plain web / SSR) — use the web fallback.
    isNative = false;
  }

  return isNative ? captureNative(quality) : captureWeb();
}
