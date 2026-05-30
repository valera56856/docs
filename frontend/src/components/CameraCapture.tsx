/**
 * CameraCapture — an in-app rear-camera viewfinder for photographing invoices.
 *
 * Renders a live `<video>` preview of the device's rear camera with a big round
 * shutter button. Tapping the shutter freezes the current frame onto an
 * offscreen `<canvas>`, encodes it to a JPEG {@link File} (~0.9 quality) via
 * {@link canvasToJpegFile}, and hands it to {@link CameraCaptureProps.onCapture}
 * — which feeds the SAME `receipts.uploadPhoto` path the page already uses. The
 * operator can take as many shots as the invoice has pages; "Готово" / the
 * close affordance ends the session and releases the camera.
 *
 * Graceful degradation is first-class: if `getUserMedia` is unsupported (old
 * WebView / insecure context), the permission is denied, or there is no camera,
 * the viewfinder is replaced by a clear Ukrainian message plus a file-input
 * fallback (`capture="environment"`, so phone browsers still open the camera).
 * The fallback is ALSO always available as a secondary action while the live
 * camera works, so a flaky camera never blocks the operator.
 *
 * Camera release is owned by {@link useCameraStream}: tracks stop on unmount,
 * when `active` flips false, and before any re-request — the hardware indicator
 * never lingers.
 *
 * Layout: mobile-first full-bleed preview + floating shutter; on desktop a
 * centered, framed preview. All controls clear the 44px touch floor and read
 * from the design tokens so light/dark reskin for free.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChangeEvent, JSX } from 'react';
import { Camera as CameraIcon, ImagePlus, RefreshCw, X } from 'lucide-react';

import { canvasToJpegFile } from '@/lib/camera';
import { useCameraStream } from '@/lib/useCameraStream';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { cn } from '@/lib/cn';

/** Props for {@link CameraCapture}. */
export interface CameraCaptureProps {
  /**
   * Receive each captured/selected page as a JPEG {@link File}. The parent
   * uploads it (e.g. `receipts.uploadPhoto`); resolve the returned promise after
   * the upload settles so the shutter re-enables only once the page is stored.
   */
  onCapture: (file: File) => Promise<void> | void;
  /**
   * Close the viewfinder and release the camera (e.g. the operator finished and
   * wants to run recognition).
   */
  onClose: () => void;
  /** How many pages have been captured so far — shown as a live counter. */
  capturedCount: number;
  /**
   * True while the parent's upload is in flight — disables the shutter so two
   * frames can't be captured before the first finishes uploading.
   */
  isBusy?: boolean;
}

/**
 * Render the in-app camera viewfinder (or its graceful fallback).
 *
 * @param props - {@link CameraCaptureProps}.
 * @returns The camera capture element.
 */
export function CameraCapture({
  onCapture,
  onClose,
  capturedCount,
  isBusy = false,
}: CameraCaptureProps): JSX.Element {
  const videoRef = useRef<HTMLVideoElement>(null);
  // One reusable offscreen canvas for frame grabs (created on first capture).
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // True only while we encode a grabbed frame — distinct from the parent's
  // upload `isBusy`, but both gate the shutter.
  const [isCapturing, setIsCapturing] = useState(false);

  const { stream, status, error, start } = useCameraStream(true);

  // Attach the live stream to the <video> element whenever it (re)appears.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    if (stream) {
      // `play()` can reject if interrupted (e.g. rapid unmount); ignore — the
      // element auto-plays via the `autoPlay` attr and we never surface this.
      void video.play().catch(() => undefined);
    }
  }, [stream]);

  /**
   * Grab the current video frame, encode it to a JPEG File, and hand it to the
   * parent. Guards against double-fires and reports nothing on its own — the
   * parent owns success/error UX around the upload.
   */
  const handleShutter = useCallback(async () => {
    const video = videoRef.current;
    if (!video || status !== 'ready' || isCapturing || isBusy) return;

    const width = video.videoWidth;
    const height = video.videoHeight;
    // Dimensions are 0 until the first frame decodes — bail rather than encode
    // an empty canvas into a blank "photo".
    if (width === 0 || height === 0) return;

    setIsCapturing(true);
    try {
      const canvas = canvasRef.current ?? document.createElement('canvas');
      canvasRef.current = canvas;
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Canvas 2D context unavailable.');
      ctx.drawImage(video, 0, 0, width, height);

      const file = await canvasToJpegFile(canvas);
      await onCapture(file);
    } finally {
      setIsCapturing(false);
    }
  }, [status, isCapturing, isBusy, onCapture]);

  /** Bridge the file-input fallback into the same `onCapture` path. */
  const handleFileChange = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      // Reset the input so picking the SAME file again still fires `change`.
      event.target.value = '';
      if (file) {
        await onCapture(file);
      }
    },
    [onCapture],
  );

  const shutterDisabled = status !== 'ready' || isCapturing || isBusy;
  const showFallback = status === 'error';

  return (
    <div
      className={cn(
        'relative flex w-full flex-1 flex-col overflow-hidden',
        'rounded-[var(--radius-lg)] border border-[var(--color-border)]',
        'bg-[var(--color-navy)]',
        // Mobile: tall, near full-bleed viewfinder. Desktop: framed + capped.
        'min-h-[60vh] md:mx-auto md:min-h-[420px] md:max-w-xl',
      )}
    >
      {/* Hidden file fallback — always mounted so it works whether the live
          camera failed or the operator just prefers an existing photo. */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        onChange={(e) => void handleFileChange(e)}
      />

      {showFallback ? (
        /* ---- Graceful fallback: message + file upload ---- */
        <div className="flex flex-1 flex-col items-center justify-center gap-[var(--space-4)] p-[var(--space-6)] text-center">
          <span
            aria-hidden
            className="flex h-16 w-16 items-center justify-center rounded-[var(--radius-full)] bg-[var(--color-danger-bg)] text-[color:var(--color-danger)]"
          >
            <CameraIcon size={28} aria-hidden />
          </span>
          <p
            role="alert"
            className="max-w-sm text-[length:var(--font-size-sm)] text-[color:var(--color-text-inverse)]"
          >
            {error?.message ??
              'Камера недоступна. Завантажте фото накладної з пам’яті.'}
          </p>
          <div className="flex w-full max-w-xs flex-col gap-[var(--space-2)]">
            <Button
              intent="primary"
              size="lg"
              fullWidth
              disabled={isBusy}
              onClick={() => fileInputRef.current?.click()}
            >
              <ImagePlus size={20} aria-hidden /> Завантажити фото
            </Button>
            {error?.canRetry && (
              <Button
                intent="secondary"
                size="lg"
                fullWidth
                disabled={isBusy}
                onClick={() => start()}
              >
                <RefreshCw size={18} aria-hidden /> Спробувати камеру ще раз
              </Button>
            )}
          </div>
        </div>
      ) : (
        /* ---- Live viewfinder ---- */
        <>
          {/* The preview itself. `playsInline` keeps iOS from going fullscreen;
              `object-cover` fills the frame; muted+autoPlay satisfy autoplay. */}
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            aria-label="Перегляд камери"
            className="absolute inset-0 h-full w-full object-cover"
          />

          {/* Connecting overlay until the first frame is ready. */}
          {status !== 'ready' && (
            <div
              className="absolute inset-0 flex flex-col items-center justify-center gap-[var(--space-2)]"
              style={{
                // `color-mix` instead of a Tailwind slash-opacity: the modifier
                // can't apply to an arbitrary `var()` color, so we blend the navy
                // token with transparent here to get a real translucent veil.
                backgroundColor:
                  'color-mix(in srgb, var(--color-navy) 80%, transparent)',
              }}
            >
              <Spinner
                size={28}
                label="Відкриваємо камеру…"
                className="text-[color:var(--color-text-inverse)]"
              />
              <p className="text-[length:var(--font-size-sm)] text-[color:var(--color-text-inverse)]">
                Відкриваємо камеру…
              </p>
            </div>
          )}

          {/* Top bar: page counter + close. Absolute so it floats on the feed. */}
          <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 p-[var(--space-3)]">
            <span
              className="rounded-[var(--radius-full)] bg-black/45 px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--font-size-sm)] font-[var(--font-weight-semibold)] text-[color:var(--color-text-inverse)]"
              aria-live="polite"
            >
              {capturedCount === 0
                ? 'Сфотографуйте сторінку'
                : `Знято сторінок: ${capturedCount}`}
            </span>
            <button
              type="button"
              aria-label="Закрити камеру"
              onClick={onClose}
              className={cn(
                'flex h-11 w-11 items-center justify-center rounded-[var(--radius-full)]',
                'bg-black/45 text-[color:var(--color-text-inverse)]',
                'hover:bg-black/60 focus-visible:outline-none',
              )}
            >
              <X size={20} aria-hidden />
            </button>
          </div>

          {/* Bottom controls: file fallback (left) + round shutter (center). */}
          <div className="absolute inset-x-0 bottom-0 flex items-center justify-center p-[var(--space-5)]">
            {/* Secondary: pick an existing file even when the camera works. */}
            <button
              type="button"
              aria-label="Завантажити фото з пам’яті"
              disabled={isBusy}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                'absolute left-[var(--space-5)] flex h-12 w-12 items-center justify-center',
                'rounded-[var(--radius-full)] bg-black/45 text-[color:var(--color-text-inverse)]',
                'hover:bg-black/60 focus-visible:outline-none',
                'disabled:cursor-not-allowed disabled:opacity-50',
              )}
            >
              <ImagePlus size={22} aria-hidden />
            </button>

            {/* Round shutter — the primary action. 72px, well over the 44px floor. */}
            <button
              type="button"
              aria-label="Зробити фото"
              disabled={shutterDisabled}
              onClick={() => void handleShutter()}
              className={cn(
                'flex h-[72px] w-[72px] items-center justify-center rounded-[var(--radius-full)]',
                'bg-white/90 ring-4 ring-white/50',
                'transition-transform duration-150 active:scale-95',
                'focus-visible:outline-none focus-visible:ring-[var(--color-blue)]',
                'disabled:cursor-not-allowed disabled:opacity-60',
              )}
            >
              {isCapturing || isBusy ? (
                <Spinner
                  size={26}
                  label={null}
                  className="text-[color:var(--color-navy)]"
                />
              ) : (
                <span className="h-14 w-14 rounded-[var(--radius-full)] bg-white shadow-[var(--shadow-md)]" />
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
