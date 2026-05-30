/**
 * CameraPage — capture one or more photos of the printed supplier invoice and
 * upload them to the already-created draft receipt.
 *
 * Flow: the receipt was created on the suppliers screen, so its id arrives via
 * the URL (`/receipt/:id/camera`). Each capture uses {@link capturePhoto}
 * (Capacitor camera on native, a file/camera input on web), uploads immediately
 * via `receipts.uploadPhoto`, and appends a thumbnail to the strip. Once at
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
import { capturePhoto, CameraCancelledError } from '@/lib/camera';
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
  const receiptId = Number(id);
  const { toast } = useToast();

  const [photos, setPhotos] = useState<UploadedPhoto[]>([]);
  /** True while a single capture+upload is in flight (disables capture). */
  const [isUploading, setIsUploading] = useState(false);
  /** True while OCR is being enqueued (disables the Розпізнати button). */
  const [isRecognizing, setIsRecognizing] = useState(false);

  /**
   * Capture a photo and upload it to the receipt, appending a thumbnail. A user
   * cancellation is silently ignored; real failures surface a toast.
   */
  const captureAndUpload = useCallback(async () => {
    if (!Number.isFinite(receiptId)) {
      toast({ variant: 'error', title: 'Невідома накладна.' });
      return;
    }
    setIsUploading(true);
    try {
      const file = await capturePhoto();
      const result = await receiptsApi.uploadPhoto(receiptId, file);
      setPhotos((prev) => [
        ...prev,
        { id: result.id, imageUrl: result.image_url },
      ]);
    } catch (error) {
      // Cancelling the camera is not an error — just stop quietly.
      if (error instanceof CameraCancelledError) {
        return;
      }
      toast({
        variant: 'error',
        title: 'Не вдалося завантажити фото',
        description: 'Спробуйте сфотографувати сторінку ще раз.',
      });
    } finally {
      setIsUploading(false);
    }
  }, [receiptId, toast]);

  /** Enqueue Gemini OCR and move to the receipt table (which polls). */
  const recognize = useCallback(async () => {
    if (photos.length === 0) {
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
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-4)] p-[var(--space-4)]">
      <header className="flex items-center justify-between gap-2">
        <h1 className="text-[var(--font-size-xl)]">Фото накладної</h1>
        <ThemeToggle />
      </header>

      {/* Preview strip / empty state */}
      {photos.length === 0 ? (
        <EmptyState
          icon={CameraIcon}
          title="Сфотографуйте накладну"
          hint="Зробіть фото паперової накладної. Можна додати кілька сторінок."
        />
      ) : (
        <ul className="grid grid-cols-3 gap-[var(--space-2)]">
          {photos.map((photo, index) => (
            <li key={photo.imageUrl} className="relative">
              <img
                src={photo.imageUrl}
                alt={`Сторінка ${index + 1}`}
                className="aspect-[3/4] w-full rounded-[var(--radius-md)] border border-[var(--color-border)] object-cover"
              />
              <span className="absolute left-1 top-1 rounded-[var(--radius-full)] bg-[var(--color-navy)] px-[var(--space-2)] py-[1px] text-[var(--font-size-xs)] text-[var(--color-text-inverse)]">
                {index + 1}
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* Capture + recognize controls */}
      <div className="mt-auto flex flex-col gap-[var(--space-2)]">
        <Button
          intent="secondary"
          size="lg"
          fullWidth
          disabled={isUploading || isRecognizing}
          onClick={() => void captureAndUpload()}
        >
          {isUploading ? (
            <>
              <Spinner size={18} label={null} /> Завантаження…
            </>
          ) : (
            <>
              <ImagePlus size={20} aria-hidden />
              {photos.length === 0 ? 'Додати фото' : 'Додати ще сторінку'}
            </>
          )}
        </Button>

        <Button
          size="lg"
          fullWidth
          disabled={photos.length === 0 || isUploading || isRecognizing}
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
    </main>
  );
}
