import { useState } from "react";
import { login } from "./auth";
import type { AuthSession } from "./types";

export default function LoginScreen({
  onLogin,
}: {
  onLogin: (session: AuthSession) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
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
          C<span>ClearPath</span>
        </div>
        <p className="login-subtitle">Transfer Review Workspace</p>
        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="login-username">Username</label>
          <input
            id="login-username"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          <button className="primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="login-hint">
          Demo credentials — username: <code>reviewer</code> · password:{" "}
          <code>LPLTeam23</code>
        </p>
        <p className="login-disclaimer">
          Independent hackathon prototype. Not endorsed by LPL Financial.
          <br />
          Unauthenticated demo — never expose publicly. Use synthetic data only.
        </p>
      </div>
    </div>
  );
}
