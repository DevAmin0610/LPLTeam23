import { describe, expect, it, beforeEach, vi } from "vitest";
import { login, logout, getSession } from "../auth";

beforeEach(() => {
  sessionStorage.clear();
});

describe("auth", () => {
  it("rejects unknown credentials", () => {
    expect(login("unknown", "wrong")).toBeNull();
  });

  it("rejects correct username with wrong password", () => {
    expect(login("reviewer", "wrongpassword")).toBeNull();
  });

  it("returns a session for valid credentials", () => {
    const session = login("reviewer", "LPLTeam23");
    expect(session).not.toBeNull();
    expect(session?.mode).toBe("demo");
    expect(session?.username).toBe("reviewer");
    expect(session?.token).toMatch(/^[0-9a-f]{36}$/);
  });

  it("keeps the local demo session in memory when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError");
    });
    expect(login("reviewer", "LPLTeam23")?.username).toBe("reviewer");
  });

  it("normalises username to lowercase", () => {
    const session = login("REVIEWER", "LPLTeam23");
    expect(session?.username).toBe("reviewer");
  });

  it("persists session so getSession returns it", () => {
    login("reviewer", "LPLTeam23");
    expect(getSession()).not.toBeNull();
    expect(getSession()?.username).toBe("reviewer");
  });

  it("logout clears the session", () => {
    login("reviewer", "LPLTeam23");
    logout();
    expect(getSession()).toBeNull();
  });

  it("getSession returns null when storage is empty", () => {
    expect(getSession()).toBeNull();
  });

  it("rejects expired Cognito sessions", () => {
    sessionStorage.setItem(
      "clearpath.session.v2",
      JSON.stringify({
        mode: "cognito",
        username: "reviewer@example.com",
        token: "expired-token",
        expires_at: Date.now() - 1,
        created_at: new Date().toISOString(),
      }),
    );
    expect(getSession()).toBeNull();
  });
});
