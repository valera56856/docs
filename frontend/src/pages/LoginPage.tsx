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
import { KeyRound, LogIn } from 'lucide-react';

import { useAuth } from '@/lib/auth';
import { ApiError } from '@/lib/api';
import { Button } from '@/components/ui/Button';
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
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-[var(--space-6)] p-[var(--space-6)]">
      <div className="flex justify-end">
        <ThemeToggle />
      </div>

      <header className="text-center">
        <h1 className="text-[var(--font-size-2xl)] text-[var(--color-navy)]">
          Valeraup
        </h1>
        <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
          Розпізнавання накладних
        </p>
      </header>

      {/* Mode toggle */}
      <div className="flex gap-2" role="tablist" aria-label="Спосіб входу">
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

      <form className="flex flex-col gap-[var(--space-4)]" onSubmit={handleSubmit}>
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
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 4))}
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
