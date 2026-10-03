import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

function jwt(claims: Record<string, unknown>): string {
  const encode = (value: object) =>
    btoa(JSON.stringify(value))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  return `${encode({ alg: "none" })}.${encode(claims)}.signature`;
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("VITE_AUTH_MODE", "cognito");
  vi.stubEnv(
    "VITE_COGNITO_DOMAIN",
    "https://clearpath.auth.us-east-1.amazoncognito.com",
  );
  vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client-id");
  vi.stubEnv("VITE_COGNITO_REDIRECT_URI", "http://localhost:3000");
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("Cognito authorization-code callback", () => {
  it("verifies state, exchanges the PKCE code, and stores the access token", async () => {
    sessionStorage.setItem("clearpath.pkce.state", "expected-state");
    sessionStorage.setItem("clearpath.pkce.verifier", "pkce-verifier");
    sessionStorage.setItem("clearpath.pkce.return", "/review");
    window.history.replaceState(
      null,
      "",
      "/?code=authorization-code&state=expected-state",
    );
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "access-token",
          id_token: jwt({ email: "reviewer@example.com", sub: "user-123" }),
          expires_in: 3600,
          token_type: "Bearer",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const auth = await import("../auth");

    const session = await auth.completeCognitoLogin();

    expect(session.mode).toBe("cognito");
    expect(session.username).toBe("reviewer@example.com");
    expect(auth.getAccessToken()).toBe("access-token");
    expect(window.location.pathname).toBe("/review");
    const request = fetch.mock.calls[0];
    expect(request[0]).toBe(
      "https://clearpath.auth.us-east-1.amazoncognito.com/oauth2/token",
    );
    const body = new URLSearchParams(String(request[1]?.body));
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(body.get("code_verifier")).toBe("pkce-verifier");
    expect(body.get("redirect_uri")).toBe("http://localhost:3000");
  });

  it("rejects a callback whose state does not match", async () => {
    sessionStorage.setItem("clearpath.pkce.state", "expected-state");
    sessionStorage.setItem("clearpath.pkce.verifier", "pkce-verifier");
    window.history.replaceState(
      null,
      "",
      "/?code=authorization-code&state=attacker-state",
    );
    const auth = await import("../auth");

    await expect(auth.completeCognitoLogin()).rejects.toThrow(
      "could not be verified",
    );
  });

  it("rejects HTTP redirect hosts that merely start with localhost", async () => {
    vi.resetModules();
    vi.stubEnv(
      "VITE_COGNITO_REDIRECT_URI",
      "http://localhost.attacker.example/callback",
    );
    const auth = await import("../auth");

    expect(auth.isCognitoConfigured()).toBe(false);
    expect(auth.getAuthConfigurationError()).toMatch(/must use HTTPS/);
  });
});
