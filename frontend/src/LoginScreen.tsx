import { useState } from "react";
import {
  beginCognitoLogin,
  getAuthConfigurationError,
  isCognitoConfigured,
  login,
} from "./auth";
import type { AuthSession } from "./types";

export default function LoginScreen({
  onLogin,
  initialError = "",
}: {
  onLogin: (session: AuthSession) => void;
  initialError?: string;
}) {
  const cognito = isCognitoConfigured();
  const configurationError = getAuthConfigurationError();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(initialError || configurationError || "");
  const [busy, setBusy] = useState(false);

  async function handleCognitoLogin() {
    setBusy(true);
    setError("");
    try {
      await beginCognitoLogin();
    } catch (reason) {
      setBusy(false);
      setError(
        reason instanceof Error ? reason.message : "Sign-in could not start.",
      );
    }
  }

  function handleDemoSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const session = login(username, password);
    setBusy(false);
    if (!session) {
      setError("Invalid username or password.");
      return;
    }
    onLogin(session);
  }

  return (
    <div className="login-backdrop">
      <div className="login-card">
        <div className="login-brand">
          <img className="login-logo" src="/clearpath.png" alt="ClearPath" />
        </div>
        <p className="login-subtitle">Transfer Review Workspace</p>
        {cognito ? (
          <div className="login-form">
            {error && (
              <div role="alert" className="error">
                {error}
              </div>
            )}
            <button
              className="primary"
              disabled={busy}
              onClick={() => void handleCognitoLogin()}
            >
              {busy ? "Redirecting…" : "Sign in securely"}
            </button>
          </div>
        ) : (
          <form onSubmit={handleDemoSubmit} className="login-form">
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {error && (
              <div role="alert" className="error">
                {error}
              </div>
            )}
            <button className="primary" disabled={busy || !!configurationError}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}
        {!cognito && !configurationError && (
          <p className="login-hint">
            Local demo credentials — username: <code>reviewer</code> · password:{" "}
            <code>LPLTeam23</code>
          </p>
        )}
        <p className="login-disclaimer">
          {cognito ? (
            "Invite-only access. Use synthetic data only."
          ) : (
            <>
              Independent hackathon prototype. Not endorsed by LPL Financial.
              <br />
              Local demo only — never expose publicly. Use synthetic data only.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
