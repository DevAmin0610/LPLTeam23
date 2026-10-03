import { describe, expect, it, beforeEach } from "vitest";
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
    expect(session?.username).toBe("reviewer");
    expect(session?.token).toMatch(/^[0-9a-f]{36}$/);
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
});
