/**
 * LoginPage — the entry screen.
 *
 * Two convenient auth paths (per the spec's "Convenient auth"):
 * - Email + password (first login / new device).
 * - Fast 4-digit PIN (returning operator on a trusted device). Biometrics will
 *   gate the PIN later via Capacitor — see TODO.
 *
 * On success the {@link useAuth} provider stores tokens and we navigate to the
 * supplier picker, the natural first step of the receipt flow. Inputs use the
 * kit {@link Input} (labelled, error-aware, 44px touch floor) so the screen
 * reskins in dark mode alongside the rest of the app.
 */
import { useState } from 'react';
import type { FormEvent, JSX } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound, LogIn, ScanLine } from 'lucide-react';

import { useAuth } from '@/lib/auth';
import { ApiError } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ThemeToggle } from '@/components/ThemeProvider';

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
    <main className="relative mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-[var(--space-6)] p-[var(--space-6)]">
      {/* Theme toggle floats top-right so the brand stays centered. */}
      <div className="absolute right-[var(--space-4)] top-[var(--space-4)]">
        <ThemeToggle />
      </div>

      {/* Brand moment: a gradient mark + confident display title. */}
      <header className="flex flex-col items-center gap-[var(--space-4)] text-center">
        <span
          aria-hidden
          className="flex h-16 w-16 items-center justify-center rounded-[var(--radius-xl)] text-[color:var(--color-on-accent)] shadow-[var(--shadow-accent)]"
          style={{ backgroundImage: 'var(--gradient-brand)' }}
        >
          <ScanLine size={32} strokeWidth={2.25} />
        </span>
        <div className="flex flex-col gap-[var(--space-1)]">
          <h1 className="text-[length:var(--font-size-3xl)] font-[var(--font-weight-bold)] text-[color:var(--color-text)]">
            Valeraup
          </h1>
          <p className="text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)]">
            Розпізнавання накладних
          </p>
        </div>
      </header>

      <Card variant="glass" className="flex flex-col gap-[var(--space-5)] p-[var(--space-5)]">
        {/* Segmented control for the auth method — quieter than two CTAs. */}
        <div
          className="grid grid-cols-2 gap-1 rounded-[var(--radius-md)] bg-[var(--color-surface-muted)] p-1"
          role="tablist"
          aria-label="Спосіб входу"
        >
          <SegTab
            label="Пароль"
            icon={LogIn}
            active={mode === 'password'}
            onClick={() => setMode('password')}
          />
          <SegTab
            label="PIN"
            icon={KeyRound}
            active={mode === 'pin'}
            onClick={() => setMode('pin')}
          />
        </div>

        <form
          className="flex flex-col gap-[var(--space-4)]"
          onSubmit={handleSubmit}
        >
          {mode === 'password' ? (
            <>
              <Input
                label="Email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <Input
                label="Пароль"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </>
          ) : (
            <>
              {/* PIN login still needs the email to identify the profile whose
                  PIN is checked. On a trusted device this would be prefilled
                  from the last login (TODO: persist + biometric gate). */}
              <Input
                label="Email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <Input
                label="4-значний PIN"
                type="password"
                inputMode="numeric"
                autoComplete="off"
                maxLength={4}
                value={code}
                onChange={(e) =>
                  setCode(e.target.value.replace(/\D/g, '').slice(0, 4))
                }
                required
              />
            </>
          )}

          {error && (
            <p
              role="alert"
              className="text-[length:var(--font-size-sm)] text-[color:var(--color-danger)]"
            >
              {error}
            </p>
          )}

          <Button type="submit" size="lg" fullWidth disabled={isSubmitting}>
            {isSubmitting ? 'Зачекайте…' : 'Увійти'}
          </Button>
        </form>
      </Card>

      {/* TODO(native): biometric unlock (Face ID / fingerprint) before PIN via
          a Capacitor biometrics plugin on supported devices. */}
    </main>
  );
}

/** Props for {@link SegTab} — one segment of the login method control. */
interface SegTabProps {
  /** Visible label (also the accessible name). */
  label: string;
  /** Leading icon. */
  icon: typeof LogIn;
  /** Whether this segment is selected. */
  active: boolean;
  /** Activate this segment. */
  onClick: () => void;
}

/**
 * One pill of the login-method segmented control. The active segment gets a
 * solid surface that "lifts" out of the track; the inactive one is flat text.
 * Kept above the 44px touch floor for thumb use.
 *
 * @param props - {@link SegTabProps}.
 * @returns The segment button.
 */
function SegTab({ label, icon: Icon, active, onClick }: SegTabProps): JSX.Element {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={[
        'flex min-h-[40px] items-center justify-center gap-2 rounded-[var(--radius-sm)]',
        'text-[length:var(--font-size-sm)] font-[var(--font-weight-semibold)]',
        'transition-[background-color,color,box-shadow] duration-150',
        'focus-visible:outline-none',
        active
          ? 'bg-[var(--color-surface)] text-[color:var(--color-text)] shadow-[var(--shadow-xs)]'
          : 'bg-transparent text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)]',
      ].join(' ')}
    >
      <Icon size={16} aria-hidden />
      {label}
    </button>
  );
}
