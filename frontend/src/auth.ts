import type { AuthSession } from "./types";

const SESSION_KEY = "clearpath.session.v2";
const VERIFIER_KEY = "clearpath.pkce.verifier";
const STATE_KEY = "clearpath.pkce.state";
const RETURN_KEY = "clearpath.pkce.return";
const AUTH_EXPIRED_EVENT = "clearpath:auth-expired";
const EXPIRY_SKEW_MS = 30_000;

const requestedMode = (
  import.meta.env.VITE_AUTH_MODE || (import.meta.env.DEV ? "demo" : "cognito")
).toLowerCase();
const cognitoDomain = (import.meta.env.VITE_COGNITO_DOMAIN || "").replace(
  /\/+$/,
  "",
);
const cognitoClientId = import.meta.env.VITE_COGNITO_CLIENT_ID || "";
const redirectUri =
  import.meta.env.VITE_COGNITO_REDIRECT_URI || window.location.origin;
const cognitoScope =
  import.meta.env.VITE_COGNITO_SCOPE || "openid email clearpath/review";

// Local development only. This gate is never backend authentication and must
// not be selected for the CloudFront build.
const DEMO_CREDENTIALS: Record<string, string> = {
  reviewer: "LPLTeam23",
  admin: "LPLTeam23",
};

let callbackPromise: Promise<AuthSession> | null = null;

function storageSet(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    throw new Error("Browser session storage is required for secure sign-in.");
  }
}

function storageGet(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageRemove(key: string): void {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* The in-memory session can still be cleared by the caller. */
  }
}

function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return bytes;
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function randomToken(): string {
  return Array.from(randomBytes(18), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

function authConfigurationError(): string | null {
  if (requestedMode === "demo") return null;
  if (requestedMode !== "cognito") {
    return "VITE_AUTH_MODE must be demo or cognito.";
  }
  if (!cognitoDomain || !cognitoClientId) {
    return "Cognito authentication is missing its domain or client ID.";
  }
  try {
    const redirect = new URL(redirectUri);
    const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(
      redirect.hostname,
    );
    if (
      redirect.protocol !== "https:" &&
      !(redirect.protocol === "http:" && loopback)
    ) {
      return "The Cognito redirect URI must use HTTPS (or an exact loopback host for development).";
    }
  } catch {
    return "The Cognito redirect URI is invalid.";
  }
  return null;
}

export function getAuthConfigurationError(): string | null {
  return authConfigurationError();
}

export function isCognitoConfigured(): boolean {
  return requestedMode === "cognito" && authConfigurationError() === null;
}

export function hasAuthCallback(): boolean {
  const query = new URLSearchParams(window.location.search);
  return query.has("code") || query.has("error");
}

export function login(username: string, password: string): AuthSession | null {
  if (requestedMode !== "demo") return null;
  if (DEMO_CREDENTIALS[username.trim().toLowerCase()] !== password) return null;
  const session: AuthSession = {
    mode: "demo",
    username: username.trim().toLowerCase(),
    token: randomToken(),
    created_at: new Date().toISOString(),
  };
  try {
    storageSet(SESSION_KEY, JSON.stringify(session));
  } catch {
    // The local-only gate can continue in React memory when storage is blocked.
  }
  return session;
}

export async function beginCognitoLogin(): Promise<void> {
  const configurationError = authConfigurationError();
  if (!isCognitoConfigured() || configurationError) {
    throw new Error(
      configurationError || "Cognito authentication is unavailable.",
    );
  }
  const verifier = base64Url(randomBytes(32));
  const state = base64Url(randomBytes(24));
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  );
  const challenge = base64Url(new Uint8Array(digest));
  storageSet(VERIFIER_KEY, verifier);
  storageSet(STATE_KEY, state);
  storageSet(RETURN_KEY, `${window.location.pathname}${window.location.hash}`);

  const authorize = new URL(`${cognitoDomain}/oauth2/authorize`);
  authorize.search = new URLSearchParams({
    response_type: "code",
    client_id: cognitoClientId,
    redirect_uri: redirectUri,
    scope: cognitoScope,
    state,
    code_challenge_method: "S256",
    code_challenge: challenge,
  }).toString();
  window.location.assign(authorize.toString());
}

function jwtClaims(token: string): Record<string, unknown> {
  const payload = token.split(".")[1];
  if (!payload)
    throw new Error("The identity provider returned an invalid token.");
  const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const value: unknown = JSON.parse(atob(padded));
  if (!value || typeof value !== "object") {
    throw new Error("The identity provider returned invalid claims.");
  }
  return value as Record<string, unknown>;
}

async function exchangeCallback(): Promise<AuthSession> {
  const configurationError = authConfigurationError();
  if (!isCognitoConfigured() || configurationError) {
    throw new Error(
      configurationError || "Cognito authentication is unavailable.",
    );
  }
  const query = new URLSearchParams(window.location.search);
  if (query.has("error")) {
    throw new Error(
      "Sign-in was cancelled or rejected by the identity provider.",
    );
  }
  const code = query.get("code");
  const state = query.get("state");
  const expectedState = storageGet(STATE_KEY);
  const verifier = storageGet(VERIFIER_KEY);
  if (
    !code ||
    !state ||
    !expectedState ||
    state !== expectedState ||
    !verifier
  ) {
    throw new Error(
      "The sign-in response could not be verified. Start sign-in again.",
    );
  }

  const response = await fetch(`${cognitoDomain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: cognitoClientId,
      code,
      redirect_uri: redirectUri,
      code_verifier: verifier,
    }),
    credentials: "omit",
  });
  if (!response.ok) {
    throw new Error("The identity provider could not complete sign-in.");
  }
  const tokens: unknown = await response.json();
  if (
    !tokens ||
    typeof tokens !== "object" ||
    !("access_token" in tokens) ||
    !("id_token" in tokens) ||
    !("expires_in" in tokens) ||
    typeof tokens.access_token !== "string" ||
    typeof tokens.id_token !== "string" ||
    typeof tokens.expires_in !== "number"
  ) {
    throw new Error("The identity provider returned an incomplete session.");
  }

  const claims = jwtClaims(tokens.id_token);
  const username = [claims.email, claims["cognito:username"], claims.sub].find(
    (value): value is string => typeof value === "string" && value.length > 0,
  );
  if (!username)
    throw new Error("The signed-in user has no usable identity claim.");

  const session: AuthSession = {
    mode: "cognito",
    username,
    token: tokens.access_token,
    id_token: tokens.id_token,
    expires_at: Date.now() + tokens.expires_in * 1000,
    created_at: new Date().toISOString(),
  };
  storageSet(SESSION_KEY, JSON.stringify(session));
  storageRemove(VERIFIER_KEY);
  storageRemove(STATE_KEY);
  const returnPath = storageGet(RETURN_KEY) || "/";
  storageRemove(RETURN_KEY);
  window.history.replaceState(null, "", returnPath);
  return session;
}

export function completeCognitoLogin(): Promise<AuthSession> {
  callbackPromise ??= exchangeCallback();
  return callbackPromise;
}

export function clearSession(): void {
  storageRemove(SESSION_KEY);
}

export function expireSession(): void {
  clearSession();
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

export function onSessionExpired(listener: () => void): () => void {
  window.addEventListener(AUTH_EXPIRED_EVENT, listener);
  return () => window.removeEventListener(AUTH_EXPIRED_EVENT, listener);
}

export function logout(): void {
  const cognitoLogout = isCognitoConfigured();
  clearSession();
  if (cognitoLogout) {
    const target = new URL(`${cognitoDomain}/logout`);
    target.search = new URLSearchParams({
      client_id: cognitoClientId,
      logout_uri: redirectUri,
    }).toString();
    window.location.assign(target.toString());
  }
}

export function getSession(): AuthSession | null {
  try {
    const raw = storageGet(SESSION_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      !parsed ||
      typeof parsed !== "object" ||
      !("mode" in parsed) ||
      !("username" in parsed) ||
      !("token" in parsed) ||
      !["demo", "cognito"].includes(String(parsed.mode)) ||
      typeof parsed.username !== "string" ||
      typeof parsed.token !== "string"
    ) {
      clearSession();
      return null;
    }
    const session = parsed as AuthSession;
    if (
      session.mode === "cognito" &&
      (!session.expires_at || session.expires_at <= Date.now() + EXPIRY_SKEW_MS)
    ) {
      clearSession();
      return null;
    }
    return session;
  } catch {
    clearSession();
    return null;
  }
}

export function getAccessToken(): string | null {
  const session = getSession();
  return session?.mode === "cognito" ? session.token : null;
}
