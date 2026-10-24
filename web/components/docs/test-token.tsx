'use client';
// "Get a test token": asks this docs site (app/api/docs/token) to sign a short-lived API token for an email and role.
// It works only when the site runs with TALNEX_DOCS_DEV_TOKENS=true, on this computer.
import { type FormEvent, useEffect, useState } from 'react';

type State =
  | { kind: 'checking' }
  | { kind: 'off' }
  | { kind: 'ready' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; token: string; expiresAt: string; role: string };

export function TestToken() {
  const [state, setState] = useState<State>({ kind: 'checking' });
  const [minutes, setMinutes] = useState(30);
  const [email, setEmail] = useState('organizer@talnex.test');
  const [role, setRole] = useState('organizer');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetch('/api/docs/token')
      .then((r) => r.json())
      .then((d: { enabled: boolean; minutes: number }) => {
        setMinutes(d.minutes);
        setState(d.enabled ? { kind: 'ready' } : { kind: 'off' });
      })
      .catch(() => setState({ kind: 'off' }));
  }, []);

  async function mint(e: FormEvent) {
    e.preventDefault();
    setCopied(false);
    const r = await fetch('/api/docs/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, role }),
    });
    const d = await r.json();
    if (!r.ok) return setState({ kind: 'error', message: d.error ?? 'Could not make a token.' });
    setState({ kind: 'done', token: d.token, expiresAt: d.expires_at, role: d.role });
  }

  async function copy(token: string) {
    await navigator.clipboard.writeText(token);
    setCopied(true);
  }

  if (state.kind === 'checking') return <div className="tx-token">Checking whether test tokens are on…</div>;
  // Signed-in people use their own session (above); the local helper is only for testing other accounts.
  if (state.kind === 'off') {
    return (
      <div className="tx-token">
        <p className="tx-token__title">Test tokens are off</p>
        <p className="tx-token__note">
          Start the docs site with <code>TALNEX_DOCS_DEV_TOKENS=true</code> to get a token here. Local testing only.
        </p>
      </div>
    );
  }

  return (
    <form className="tx-token" onSubmit={mint}>
      <p className="tx-token__title">Get a test token</p>
      <p className="tx-token__note">
        Local testing only. The token is signed on this computer with the API&apos;s <code>AUTH_SECRET</code>, which
        never reaches your browser, and lasts {minutes} minutes.
      </p>
      <div className="tx-token__row">
        <label className="tx-token__field">
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        </label>
        <label className="tx-token__field">
          Role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="organizer">organizer</option>
            <option value="recruiter">recruiter</option>
          </select>
        </label>
        <button type="submit" className="button button--primary">Get token</button>
      </div>
      {state.kind === 'error' ? <p className="tx-token__error">{state.message}</p> : null}
      {state.kind === 'done' ? (
        <div className="tx-token__result">
          <code className="tx-token__value">{state.token}</code>
          <div className="tx-token__row">
            <button type="button" className="button button--ghost" onClick={() => copy(state.token)}>
              {copied ? 'Copied' : 'Copy token'}
            </button>
            <span className="tx-token__note">
              {state.role} token, works until {new Date(state.expiresAt).toLocaleTimeString()}
            </span>
          </div>
          <p className="tx-token__note">
            In any endpoint&apos;s playground, open <strong>Authorization</strong>: the field already starts with{' '}
            <code>Bearer </code>. Paste the token after it so it reads <code>Bearer &lt;token&gt;</code>, then press{' '}
            <strong>Send</strong>.
          </p>
        </div>
      ) : null}
    </form>
  );
}

type Session =
  | { kind: 'idle' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; token: string; expiresAt: string; role: string; email: string };

/** "Use my session": a short-lived token for whoever is signed in to the website, to try the API as yourself. */
export function SessionToken() {
  const [state, setState] = useState<Session>({ kind: 'idle' });
  const [copied, setCopied] = useState(false);

  async function copy(token: string) {
    await navigator.clipboard.writeText(token);
    setCopied(true);
  }

  async function use() {
    setCopied(false);
    const r = await fetch('/api/docs/session-token', { method: 'POST' });
    const d = await r.json();
    if (!r.ok) return setState({ kind: 'error', message: d.error ?? 'Could not make a token.' });
    setState({ kind: 'done', token: d.token, expiresAt: d.expires_at, role: d.role, email: d.email });
    await copy(d.token).catch(() => undefined);
  }

  return (
    <div className="tx-token">
      <p className="tx-token__title">Use my session</p>
      <p className="tx-token__note">
        Signed in to TalNex? Get a short-lived token for your own account and call the API as yourself. It is copied for
        you: paste it after <code>Bearer </code> in any playground&apos;s Authorization field, then press Send.
      </p>
      <div className="tx-token__row">
        <button type="button" className="button button--primary" onClick={use}>
          Use my session
        </button>
        {state.kind === 'error' ? (
          <span className="tx-token__error">
            {state.message} <a href="/login">Sign in</a>
          </span>
        ) : null}
      </div>
      {state.kind === 'done' ? (
        <div className="tx-token__result">
          <code className="tx-token__value">{state.token}</code>
          <div className="tx-token__row">
            <button type="button" className="button button--ghost" onClick={() => copy(state.token)}>
              {copied ? 'Copied' : 'Copy token'}
            </button>
            <span className="tx-token__note">
              {state.email} ({state.role || 'no role yet'}), works until {new Date(state.expiresAt).toLocaleTimeString()}
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
