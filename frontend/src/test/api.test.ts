import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, safePreview, validatePdf } from "../api";

beforeEach(() => {
  sessionStorage.clear();
});

describe("frontend boundaries", () => {
  it("rejects empty and non-PDF selections", () => {
    expect(validatePdf(new File([], "sample.pdf"))).not.toBeNull();
    expect(validatePdf(new File(["text"], "sample.txt"))).not.toBeNull();
    expect(validatePdf(new File(["%PDF-"], "sample.pdf"))).toBeNull();
  });
  it("adds a Cognito access token to API requests", async () => {
    sessionStorage.setItem(
      "clearpath.session.v2",
      JSON.stringify({
        mode: "cognito",
        username: "reviewer@example.com",
        token: "access-token",
        expires_at: Date.now() + 60_000,
        created_at: new Date().toISOString(),
      }),
    );
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          mode: "aws",
          banner: "AWS",
          privacy_notice: "Synthetic",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await api.config();

    const headers = new Headers(fetch.mock.calls[0][1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer access-token");
  });

  it("uses authenticated fetch for protected PDF documents", async () => {
    sessionStorage.setItem(
      "clearpath.session.v2",
      JSON.stringify({
        mode: "cognito",
        username: "reviewer@example.com",
        token: "pdf-access-token",
        expires_at: Date.now() + 60_000,
        created_at: new Date().toISOString(),
      }),
    );
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["%PDF-test"], { type: "application/pdf" }), {
        status: 200,
        headers: { "Content-Type": "application/pdf" },
      }),
    );

    const document = await api.documentPdf("case-id", "document-id");

    expect(document.type).toBe("application/pdf");
    const headers = new Headers(fetch.mock.calls[0][1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer pdf-access-token");
    expect(fetch.mock.calls[0][0]).toContain(
      "/api/cases/case-id/documents/document-id",
    );
  });

  it("excludes storage metadata from the preview", () => {
    expect(
      safePreview({
        result: "mismatch",
        storage_key: "private",
        nested: { token: "private" },
      }),
    ).toEqual({ result: "mismatch", nested: {} });
  });
});
