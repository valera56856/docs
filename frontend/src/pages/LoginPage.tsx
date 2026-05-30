/**
 * LoginPage — the entry screen.
 *
 * Two convenient auth paths (per the spec's "Convenient auth"):
 * - Email + password (first login / new device).
 * - Fast 4-digit PIN (returning operator on a trusted device). Biometrics will
 *   gate the PIN later via Capacitor — see TODO.
 *
 * On success the {@link useAuth} provider stores tokens and we navigate to the
 * supplier picker, the natural first step of the receipt flow.
 */
import { useState } from 'react';
import type { FormEvent, HTMLAttributes, JSX } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound, LogIn } from 'lucide-react';

import { useAuth } from '@/lib/auth';
import { ApiError } from '@/lib/api';
import { cn } from '@/lib/cn';
import { Button } from '@/components/ui/Button';

/** Which auth method the form is currently showing. */
type Mode = 'password' | 'pin';

/**
 * Render the login screen.
 *
 * @returns The login page element.
 */
export function LoginPage(): JSX.Element {
  const { login, pin } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Handle either form submission. Disables the button while in flight and
   * surfaces a friendly Ukrainian error on failure.
   */
  async function handleSubmit(e: FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      if (mode === 'password') {
        await login(email, password);
      } else {
        await pin(email, code);
      }
      // Land on the supplier picker — first step of shooting an invoice.
      navigate('/suppliers', { replace: true });
    } catch (err) {
      // TODO(ux): map specific status codes (401 vs 5xx) to distinct messages.
      const msg =
        err instanceof ApiError && err.status === 401
          ? 'Невірні дані для входу.'
          : 'Не вдалося увійти. Спробуйте ще раз.';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-[var(--space-6)] p-[var(--space-6)]">
      <header className="text-center">
        <h1 className="text-[var(--font-size-2xl)] text-[var(--color-navy)]">
          Valeraup
        </h1>
        <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
          Розпізнавання накладних
        </p>
      </header>

      {/* Mode toggle */}
      <div
        className="flex gap-2"
        role="tablist"
        aria-label="Спосіб входу"
      >
        <Button
          role="tab"
          aria-selected={mode === 'password'}
          intent={mode === 'password' ? 'primary' : 'secondary'}
          fullWidth
          onClick={() => setMode('password')}
        >
          <LogIn size={18} aria-hidden /> Пароль
        </Button>
        <Button
          role="tab"
          aria-selected={mode === 'pin'}
          intent={mode === 'pin' ? 'primary' : 'secondary'}
          fullWidth
          onClick={() => setMode('pin')}
        >
          <KeyRound size={18} aria-hidden /> PIN
        </Button>
      </div>

      <form
        className="flex flex-col gap-[var(--space-4)]"
        onSubmit={handleSubmit}
      >
        {mode === 'password' ? (
          <>
            <Field
              id="email"
              label="Email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={setEmail}
              required
            />
            <Field
              id="password"
              label="Пароль"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={setPassword}
              required
            />
          </>
        ) : (
          <>
            {/* PIN login still needs the email to identify the profile whose
                PIN is checked. On a trusted device this would be prefilled
                from the last login (TODO: persist + biometric gate). */}
            <Field
              id="pin-email"
              label="Email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={setEmail}
              required
            />
            <Field
              id="pin"
              label="4-значний PIN"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={4}
              value={code}
              onChange={(v) => setCode(v.replace(/\D/g, '').slice(0, 4))}
              required
            />
          </>
        )}

        {error && (
          <p
            role="alert"
            className="text-[var(--font-size-sm)] text-[var(--color-danger)]"
          >
            {error}
          </p>
        )}

        <Button type="submit" size="lg" fullWidth disabled={isSubmitting}>
          {isSubmitting ? 'Зачекайте…' : 'Увійти'}
        </Button>
      </form>

      {/* TODO(native): biometric unlock (Face ID / fingerprint) before PIN via
          a Capacitor biometrics plugin on supported devices. */}
    </main>
  );
}

/** Props for the small labelled {@link Field} input helper. */
interface FieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  maxLength?: number;
  autoComplete?: string;
  inputMode?: HTMLAttributes<HTMLInputElement>['inputMode'];
}

/**
 * A labelled text input that respects the 44px touch minimum.
 *
 * @param props - {@link FieldProps}.
 * @returns The labelled input group.
 */
function Field({
  id,
  label,
  value,
  onChange,
  type = 'text',
  required,
  maxLength,
  autoComplete,
  inputMode,
}: FieldProps): JSX.Element {
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={id}
        className="text-[var(--font-size-sm)] font-[var(--font-weight-medium)]"
      >
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        required={required}
        maxLength={maxLength}
        autoComplete={autoComplete}
        inputMode={inputMode}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'min-h-[var(--touch-target-min)] rounded-[var(--radius-md)]',
          'border border-[var(--color-border)] px-[var(--space-3)]',
        )}
      />
    </div>
  );
}
