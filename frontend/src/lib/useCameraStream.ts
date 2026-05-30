/**
 * useCameraStream — open the device's rear camera as a live {@link MediaStream}
 * and keep its lifecycle honest.
 *
 * WHY a dedicated hook: `getUserMedia` returns a stream whose tracks keep the
 * camera hardware (and the recording indicator) ON until *every* track is
 * stopped. React effects can re-run and components unmount mid-flight, so the
 * "request → attach → STOP all tracks" dance is easy to get subtly wrong and
 * leak the camera. Centralizing it here means `CameraCapture` (and any future
 * caller) gets correct release for free: tracks are stopped on unmount, on an
 * explicit {@link CameraStreamControls.stop}, and before any re-request.
 *
 * It NEVER throws — a failure to open the camera is a *state*, not an exception,
 * because the page must degrade gracefully to the file-input fallback. The
 * `error` field carries a typed reason so the UI can show a friendly Ukrainian
 * message and decide whether to offer "retry" (transient) or just the fallback
 * (unsupported / denied / no camera).
 *
 * Secure-context note: `navigator.mediaDevices` is only defined in a secure
 * context (https or localhost). Prod is https and localhost counts as secure,
 * so the only realistic "unsupported" case is an old/embedded WebView — which we
 * detect up front and report as `unsupported` rather than crashing.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Why the camera could not be opened — drives the fallback message + whether a
 * retry makes sense.
 *
 * - `unsupported` — no `getUserMedia` (insecure context / old WebView). No retry.
 * - `denied` — the user blocked the camera permission (`NotAllowedError`,
 *   `SecurityError`). Retry only helps after they change the browser setting.
 * - `not-found` — no camera device exists (`NotFoundError`,
 *   `OverconstrainedError`). No retry.
 * - `in-use` — the camera is held by another app/tab (`NotReadableError`,
 *   `AbortError`). Retry can succeed once it frees up.
 * - `unknown` — anything else; retry is offered.
 */
export type CameraErrorKind =
  | 'unsupported'
  | 'denied'
  | 'not-found'
  | 'in-use'
  | 'unknown';

/** A typed, user-presentable camera failure. */
export interface CameraStreamError {
  /** Machine-readable reason (drives copy + retry affordance). */
  kind: CameraErrorKind;
  /** Friendly Ukrainian message safe to render directly. */
  message: string;
  /** Whether re-requesting the stream could plausibly succeed. */
  canRetry: boolean;
}

/** Connection lifecycle of the camera stream. */
export type CameraStatus = 'idle' | 'requesting' | 'ready' | 'error';

/** What {@link useCameraStream} returns. */
export interface CameraStreamControls {
  /** The live stream once `status === 'ready'`, else `null`. */
  stream: MediaStream | null;
  /** Current lifecycle state. */
  status: CameraStatus;
  /** Populated only when `status === 'error'`. */
  error: CameraStreamError | null;
  /**
   * (Re)request the rear camera. Safe to call repeatedly: any existing stream is
   * stopped first so we never stack live tracks. A no-op while a request is
   * already in flight.
   */
  start: () => void;
  /** Stop every track and release the camera. Idempotent. */
  stop: () => void;
}

/**
 * Map a `getUserMedia` rejection to a typed, friendly {@link CameraStreamError}.
 *
 * The DOM spec names these errors but typing is loose (`unknown`), so we read
 * `name` defensively. Messages are intentionally short and Ukrainian — they are
 * rendered verbatim next to the file-input fallback.
 *
 * @param err - The value thrown by `getUserMedia` (usually a `DOMException`).
 * @returns The classified error.
 */
function classifyError(err: unknown): CameraStreamError {
  const name = err instanceof DOMException ? err.name : '';
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return {
        kind: 'denied',
        message:
          'Доступ до камери заборонено. Дозвольте камеру в налаштуваннях браузера або завантажте фото з пам’яті.',
        canRetry: true,
      };
    case 'NotFoundError':
    case 'OverconstrainedError':
      return {
        kind: 'not-found',
        message:
          'Камеру не знайдено на цьому пристрої. Завантажте фото накладної з файлів.',
        canRetry: false,
      };
    case 'NotReadableError':
    case 'AbortError':
      return {
        kind: 'in-use',
        message:
          'Камера зайнята іншою програмою. Закрийте її та спробуйте ще раз або завантажте фото.',
        canRetry: true,
      };
    default:
      return {
        kind: 'unknown',
        message:
          'Не вдалося відкрити камеру. Спробуйте ще раз або завантажте фото з пам’яті.',
        canRetry: true,
      };
  }
}

/**
 * Manage a rear-camera {@link MediaStream} with correct release semantics.
 *
 * @param active - When `false`, the hook stays idle and releases any stream
 *   (e.g. the page is in fallback mode or the camera UI is closed). When `true`,
 *   it auto-requests the stream on mount / when it flips to `true`.
 * @returns {@link CameraStreamControls} — the stream, status, typed error, and
 *   `start` / `stop`.
 * @example
 * const { stream, status, error, start } = useCameraStream(inCaptureMode);
 * useEffect(() => { if (videoRef.current && stream) videoRef.current.srcObject = stream; }, [stream]);
 */
export function useCameraStream(active: boolean): CameraStreamControls {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [status, setStatus] = useState<CameraStatus>('idle');
  const [error, setError] = useState<CameraStreamError | null>(null);

  // Hold the live stream in a ref too so cleanup/stop never depends on a stale
  // render closure — the effect cleanup must always see the *current* tracks.
  const streamRef = useRef<MediaStream | null>(null);
  // Guards against a resolved getUserMedia landing after we've torn down (the
  // component unmounted, or a newer request superseded this one): we'd otherwise
  // attach an orphan stream and leak the camera.
  const requestSeq = useRef(0);

  const stop = useCallback(() => {
    requestSeq.current += 1; // invalidate any in-flight request
    const current = streamRef.current;
    if (current) {
      current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setStream(null);
    setStatus('idle');
  }, []);

  const start = useCallback(() => {
    // Feature-detect inside the secure-context-only `mediaDevices` namespace.
    if (
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices ||
      typeof navigator.mediaDevices.getUserMedia !== 'function'
    ) {
      setStream(null);
      setStatus('error');
      setError({
        kind: 'unsupported',
        message:
          'Зйомка в застосунку недоступна в цьому браузері. Завантажте фото накладної з пам’яті.',
        canRetry: false,
      });
      return;
    }

    // Stop a prior stream before requesting a new one so tracks never stack.
    const previous = streamRef.current;
    if (previous) {
      previous.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    const seq = (requestSeq.current += 1);
    setStatus('requesting');
    setError(null);

    navigator.mediaDevices
      .getUserMedia({
        // `ideal` (not `exact`) so laptops with only a front camera still open
        // one instead of failing with OverconstrainedError.
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      })
      .then((media) => {
        // Superseded or torn down while awaiting permission → release immediately.
        if (seq !== requestSeq.current) {
          media.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = media;
        setStream(media);
        setStatus('ready');
      })
      .catch((err: unknown) => {
        if (seq !== requestSeq.current) return; // superseded → ignore
        setStream(null);
        setStatus('error');
        setError(classifyError(err));
      });
  }, []);

  // Drive the stream from `active`: request when entering capture mode, release
  // when leaving it or on unmount. The cleanup stops tracks via the ref so it is
  // immune to stale closures.
  useEffect(() => {
    if (active) {
      start();
    } else {
      stop();
    }
    return () => {
      requestSeq.current += 1;
      const current = streamRef.current;
      if (current) {
        current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    };
  }, [active, start, stop]);

  return { stream, status, error, start, stop };
}
