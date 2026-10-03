import type { AuthSession } from "./types";

const SESSION_KEY = "clearpath.session.v1";

// Demo-only credential check. There is no backend auth; this is a local gate
// that prevents accidental exposure of the unauthenticated demo UI.
// Public deployment requires real server-side authentication.
const DEMO_CREDENTIALS: Record<string, string> = {
  reviewer: "LPLTeam23",
  admin: "LPLTeam23",
};

function randomToken(): string {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function login(username: string, password: string): AuthSession | null {
  if (DEMO_CREDENTIALS[username.trim().toLowerCase()] !== password) return null;
  const session: AuthSession = {
    username: username.trim().toLowerCase(),
    token: randomToken(),
    created_at: new Date().toISOString(),
  };
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    /* sessionStorage unavailable; session lives only in memory */
  }
  return session;
}

export function logout(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function getSession(): AuthSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === "object" &&
      "username" in parsed &&
      "token" in parsed &&
      typeof (parsed as AuthSession).token === "string"
    )
      return parsed as AuthSession;
  } catch {
    /* corrupt storage */
  }
  return null;
}
