/**
 * CameraPage — capture one or more photos of the printed supplier invoice.
 *
 * On native (Capacitor) this uses `@capacitor/camera` to open the device camera
 * and return image data; on the web it falls back to a file `<input capture>`.
 * Captured images are uploaded (R2) and their URLs attached to a new draft
 * receipt via `POST /api/receipts/`, after which we kick off recognition and
 * move to the receipt table.
 *
 * STUB STATUS: capture + upload are sketched with clear TODOs. The supplier id
 * arrives via router state from {@link SuppliersPage}.
 */
import { useCallback, useState } from 'react';
import type { JSX } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Camera as CameraIcon, ImagePlus, Trash2 } from 'lucide-react';

import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { Button } from '@/components/ui/Button';
import type { Receipt } from '@/types';

/** Router state passed from the supplier picker. */
interface CameraRouteState {
  supplierId?: number;
}

/** A locally captured photo awaiting upload. */
interface LocalPhoto {
  /** Object URL for preview. */
  previewUrl: string;
  /** Raw blob to upload to storage. */
  blob: Blob;
}

/**
 * Render the camera capture screen.
 *
 * @returns The camera page element.
 */
export function CameraPage(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const supplierId = (location.state as CameraRouteState | null)?.supplierId;

  const [photos, setPhotos] = useState<LocalPhoto[]>([]);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Capture a photo.
   *
   * TODO(native): use `Camera.getPhoto({ resultType: CameraResultType.Uri })`
   * from `@capacitor/camera`, then fetch the URI into a Blob. The hidden file
   * input below is the web fallback.
   */
  const handleFiles = useCallback((files: FileList | null) => {
    if (!files) return;
    const next: LocalPhoto[] = Array.from(files).map((file) => ({
      previewUrl: URL.createObjectURL(file),
      blob: file,
    }));
    setPhotos((prev) => [...prev, ...next]);
  }, []);

  /** Remove a captured photo before upload. */
  const removePhoto = useCallback((index: number) => {
    setPhotos((prev) => {
      URL.revokeObjectURL(prev[index]?.previewUrl ?? '');
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  /**
   * Create the draft receipt from the captured photos and start recognition.
   *
   * TODO(storage): upload each blob to R2 (presigned URL flow) and send the
   * resulting URLs as `photo_urls`. For now we send placeholder URLs so the
   * shape is correct end-to-end.
   */
  const submit = useCallback(async () => {
    if (!supplierId) {
      setError('Не обрано постачальника. Поверніться назад.');
      return;
    }
    if (photos.length === 0) {
      setError('Додайте хоча б одне фото накладної.');
      return;
    }
    setIsWorking(true);
    setError(null);
    try {
      // TODO(storage): replace previewUrl with the uploaded R2 URL.
      const receipt = await api.post<Receipt>('/receipts/', {
        supplier: supplierId,
        photo_urls: photos.map((p) => p.previewUrl),
      });
      // Enqueue Gemini OCR; the table screen polls for completion.
      await api.post(`/receipts/${receipt.id}/recognize/`);
      navigate(`/receipt/${receipt.id}`, { replace: true });
    } catch {
      setError('Не вдалося створити накладну. Спробуйте ще раз.');
    } finally {
      setIsWorking(false);
    }
  }, [supplierId, photos, navigate]);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-4)] p-[var(--space-4)]">
      <h1 className="text-[var(--font-size-xl)]">Фото накладної</h1>

      {/* Preview grid / empty state */}
      {photos.length === 0 ? (
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-[var(--space-8)] text-center">
          <CameraIcon
            size={32}
            aria-hidden
            className="mx-auto text-[var(--color-text-muted)]"
          />
          <p className="mt-[var(--space-2)] text-[var(--color-text-muted)]">
            Сфотографуйте паперову накладну. Можна додати кілька сторінок.
          </p>
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-[var(--space-2)]">
          {photos.map((photo, index) => (
            <li key={photo.previewUrl} className="relative">
              <img
                src={photo.previewUrl}
                alt={`Сторінка ${index + 1}`}
                className="aspect-[3/4] w-full rounded-[var(--radius-md)] object-cover"
              />
              <Button
                intent="danger"
                size="icon"
                aria-label={`Видалити сторінку ${index + 1}`}
                className="absolute right-1 top-1 h-9 w-9"
                onClick={() => removePhoto(index)}
              >
                <Trash2 size={16} aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p role="alert" className="text-[var(--color-danger)]">
          {error}
        </p>
      )}

      {/* Capture controls */}
      <div className="flex flex-col gap-[var(--space-2)]">
        <label
          className={cn(
            'flex min-h-[var(--touch-target-min)] cursor-pointer items-center',
            'justify-center gap-2 rounded-[var(--radius-md)]',
            'border border-[var(--color-border)] bg-[var(--color-surface)]',
            'px-[var(--space-4)] font-[var(--font-weight-semibold)]',
            'hover:bg-[var(--color-surface-muted)]',
          )}
        >
          <ImagePlus size={20} aria-hidden /> Додати фото
          {/* Web fallback; native build swaps for @capacitor/camera. */}
          <input
            type="file"
            accept="image/*"
            capture="environment"
            multiple
            className="sr-only"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </label>

        <Button
          size="lg"
          fullWidth
          disabled={isWorking}
          onClick={() => void submit()}
        >
          {isWorking ? 'Обробка…' : 'Розпізнати'}
        </Button>
      </div>
    </main>
  );
}
