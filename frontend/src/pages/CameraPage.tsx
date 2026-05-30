/**
 * CameraPage — capture one or more photos of the printed supplier invoice and
 * upload them to the draft receipt.
 *
 * Two entry shapes share this one component:
 * - **Scan-first** (`/receipt/new`, the primary flow): there is no receipt yet.
 *   The operator photographs the invoice WITHOUT picking a supplier first; we
 *   lazily create a supplier-less draft (`receipts.create()`) on the first
 *   capture, then carry the new id forward. Recognition later auto-detects the
 *   supplier from the invoice header.
 * - **Supplier-first** (`/receipt/:id/camera`, legacy): the draft already exists
 *   (created on the suppliers screen) and its id arrives via the URL.
 *
 * Capture has two surfaces, both converging on the SAME upload path
 * (`receipts.uploadPhoto`) so the scan-first flow is preserved verbatim:
 * - **In-app camera** ({@link CameraCapture}): a live `<video>` viewfinder with a
 *   round shutter that grabs the frame to a `<canvas>` → JPEG `File`. This is the
 *   primary, fastest surface — the operator never leaves the app.
 * - **File / OS-camera fallback** ({@link capturePhoto}): a hidden
 *   `<input capture="environment">` (or the Capacitor camera on native). Used
 *   automatically when `getUserMedia` is unsupported / denied / has no camera,
 *   and offered as a secondary action otherwise.
 *
 * Each capture uploads immediately and appends a thumbnail to the strip. Once at
 * least one page is uploaded the big "Розпізнати" button enqueues OCR and moves
 * to the receipt table, which polls for completion.
 *
 * We upload eagerly (per capture) rather than batching at the end so a flaky
 * warehouse connection fails one page at a time, the operator sees progress, and
 * the bytes are guaranteed on the server before recognition starts.
 */
import { useCallback, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Camera as CameraIcon, ImagePlus, ScanLine } from 'lucide-react';

import { receipts as receiptsApi } from '@/lib/api';
import {
  capturePhoto,
  CameraCancelledError,
  downscaleImage,
} from '@/lib/camera';
import { CameraCapture } from '@/components/CameraCapture';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Spinner } from '@/components/ui/Spinner';
import { ThemeToggle } from '@/components/ThemeProvider';
import { useToast } from '@/components/ui/Toast';

/** An uploaded invoice page shown in the thumbnail strip. */
interface UploadedPhoto {
  /** Backend photo id. */
  id: number;
  /** Stored image URL (used as the thumbnail src + React key). */
  imageUrl: string;
}

/**
 * Render the camera capture + upload screen.
 *
 * @returns The camera page element.
 */
export function CameraPage(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  /**
   * The receipt id we upload to. It starts from the URL (supplier-first path) or
   * `null` in scan-first mode (`/receipt/new`), where we create the draft lazily
   * on the first capture. Tracked in state so a scan-first draft, once created,
   * is reused for every subsequent page in the same session.
   */
  const urlReceiptId = id !== undefined ? Number(id) : null;
  const [receiptId, setReceiptId] = useState<number | null>(
    urlReceiptId !== null && Number.isFinite(urlReceiptId) ? urlReceiptId : null,
  );
  const { toast } = useToast();

  const [photos, setPhotos] = useState<UploadedPhoto[]>([]);
  /**
   * Whether the live in-app viewfinder is open. When `true` we mount
   * {@link CameraCapture}, which acquires the camera; closing it releases the
   * hardware. The thumbnail strip + recognize controls show when `false`.
   */
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  /** True while a single capture+upload is in flight (disables capture). */
  const [isUploading, setIsUploading] = useState(false);
  /** True while OCR is being enqueued (disables the Розпізнати button). */
  const [isRecognizing, setIsRecognizing] = useState(false);

  /**
   * Upload one captured page to the receipt, appending a thumbnail.
   *
   * This is the single upload path shared by BOTH capture surfaces (the in-app
   * camera and the OS/file fallback). In scan-first mode the draft does not
   * exist yet, so we lazily create a supplier-less one (`receipts.create()`) on
   * the first page and keep its id for subsequent pages. Failures surface a
   * toast; we never create an empty draft because the file already exists here.
   *
   * @param file - The captured invoice page as a JPEG {@link File}.
   */
  const uploadFile = useCallback(
    async (file: File) => {
      setIsUploading(true);
      try {
        // Lazily create the scan-first draft (no supplier) on the first page.
        let targetId = receiptId;
        if (targetId === null) {
          const draft = await receiptsApi.create();
          targetId = draft.id;
          setReceiptId(draft.id);
        }

        // Shrink big phone photos before upload — faster upload + OCR, same
        // legibility. Falls back to the original if it can't be re-encoded.
        const optimized = await downscaleImage(file);
        const result = await receiptsApi.uploadPhoto(targetId, optimized);
        setPhotos((prev) => [
          ...prev,
          { id: result.id, imageUrl: result.image_url },
        ]);
      } catch {
        toast({
          variant: 'error',
          title: 'Не вдалося завантажити фото',
          description: 'Спробуйте сфотографувати сторінку ще раз.',
        });
      } finally {
        setIsUploading(false);
      }
    },
    [receiptId, toast],
  );

  /**
   * Capture via the OS/file fallback ({@link capturePhoto}) and upload it.
   *
   * Used by the "Завантажити фото" secondary action on the strip view (and on
   * native via the Capacitor camera). A user cancellation is silently ignored.
   */
  const captureViaFallback = useCallback(async () => {
    let file: File;
    try {
      file = await capturePhoto();
    } catch (error) {
      // Cancelling the picker is not an error — just stop quietly.
      if (error instanceof CameraCancelledError) {
        return;
      }
      toast({
        variant: 'error',
        title: 'Не вдалося отримати фото',
        description: 'Спробуйте ще раз.',
      });
      return;
    }
    await uploadFile(file);
  }, [uploadFile, toast]);

  /** Enqueue Gemini OCR and move to the receipt table (which polls). */
  const recognize = useCallback(async () => {
    if (photos.length === 0 || receiptId === null) {
      toast({
        variant: 'warning',
        title: 'Додайте хоча б одне фото',
        description: 'Сфотографуйте сторінку накладної перед розпізнаванням.',
      });
      return;
    }
    setIsRecognizing(true);
    try {
      await receiptsApi.recognize(receiptId);
      navigate(`/receipt/${receiptId}`, { replace: true });
    } catch {
      toast({
        variant: 'error',
        title: 'Не вдалося запустити розпізнавання',
        description: 'Спробуйте ще раз.',
      });
      setIsRecognizing(false);
    }
  }, [photos.length, receiptId, navigate, toast]);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-4)] p-[var(--space-4)] md:max-w-2xl md:gap-[var(--space-6)] md:py-[var(--space-8)]">
      <header className="flex items-center justify-between gap-2">
        <div className="flex flex-col gap-[var(--space-1)]">
          <h1 className="text-[length:var(--font-size-xl)] md:text-[length:var(--font-size-2xl)]">
            Фото накладної
          </h1>
          <p className="hidden text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)] md:block">
            Сфотографуйте всі сторінки накладної, потім запустіть розпізнавання.
            Постачальник визначиться автоматично.
          </p>
        </div>
        {/* AppShell supplies the toggle on desktop. */}
        <span className="lg:hidden">
          <ThemeToggle />
        </span>
      </header>

      {isCameraOpen ? (
        /* Live in-app viewfinder — captures feed the same upload path. */
        <CameraCapture
          onCapture={uploadFile}
          onClose={() => setIsCameraOpen(false)}
          capturedCount={photos.length}
          isBusy={isUploading}
        />
      ) : (
        <>
          {/* Preview strip / empty state */}
          {photos.length === 0 ? (
            <EmptyState
              icon={CameraIcon}
              title="Сфотографуйте накладну"
              hint="Зробіть фото паперової накладної. Можна додати кілька сторінок."
            />
          ) : (
            <ul className="grid grid-cols-3 gap-[var(--space-2)] md:grid-cols-4 md:gap-[var(--space-3)]">
              {photos.map((photo, index) => (
                <li key={photo.imageUrl} className="relative">
                  <img
                    src={photo.imageUrl}
                    alt={`Сторінка ${index + 1}`}
                    className="aspect-[3/4] w-full rounded-[var(--radius-md)] border border-[var(--color-border)] object-cover"
                  />
                  <span className="absolute left-1 top-1 rounded-[var(--radius-full)] bg-[var(--color-navy)] px-[var(--space-2)] py-[1px] text-[length:var(--font-size-xs)] text-[color:var(--color-text-inverse)]">
                    {index + 1}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {/* Capture + recognize controls */}
          <div className="mt-auto flex flex-col gap-[var(--space-2)] md:mx-auto md:w-full md:max-w-md">
            <Button
              size="lg"
              fullWidth
              disabled={isUploading || isRecognizing}
              onClick={() => setIsCameraOpen(true)}
            >
              <CameraIcon size={20} aria-hidden />
              {photos.length === 0 ? 'Відкрити камеру' : 'Додати ще сторінку'}
            </Button>

            <Button
              intent="secondary"
              size="lg"
              fullWidth
              disabled={isUploading || isRecognizing}
              onClick={() => void captureViaFallback()}
            >
              {isUploading ? (
                <>
                  <Spinner size={18} label={null} /> Завантаження…
                </>
              ) : (
                <>
                  <ImagePlus size={20} aria-hidden /> Завантажити фото
                </>
              )}
            </Button>

            <Button
              size="lg"
              fullWidth
              disabled={
                photos.length === 0 ||
                receiptId === null ||
                isUploading ||
                isRecognizing
              }
              onClick={() => void recognize()}
            >
              {isRecognizing ? (
                <>
                  <Spinner size={18} label={null} /> Запуск…
                </>
              ) : (
                <>
                  <ScanLine size={20} aria-hidden /> Розпізнати
                </>
              )}
            </Button>
          </div>
        </>
      )}
    </main>
  );
}
