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

it("sends explicit replacement intent through the AWS presign and completion flow", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          document_id: "replacement-id",
          url: "https://s3.example.test/upload",
          fields: { key: "new-key" },
          expires_in: 300,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ id: "replacement-id", status: "uploaded" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
  const result = await api.upload(
    "case-id",
    new File(["%PDF-test"], "synthetic.pdf"),
    "client_profile",
    "aws",
    true,
  );
  expect(JSON.parse(fetch.mock.calls[0][1]?.body as string)).toMatchObject({
    replace: true,
    document_type: "client_profile",
  });
  expect(fetch.mock.calls[1][1]?.credentials).toBe("omit");
  expect(fetch.mock.calls[2][0]).toContain(
    "/documents/replacement-id/complete",
  );
  expect(result.id).toBe("replacement-id");
});

it("does not confirm or replace a document when the S3 upload fails", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          document_id: "replacement-id",
          url: "https://s3.example.test/upload",
          fields: { key: "new-key" },
          expires_in: 300,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    )
    .mockResolvedValueOnce(new Response(null, { status: 403 }));
  await expect(
    api.upload(
      "case-id",
      new File(["%PDF-test"], "synthetic.pdf"),
      "account_statement",
      "aws",
      true,
    ),
  ).rejects.toThrow("storage upload failed");
  expect(fetch).toHaveBeenCalledTimes(2);
});
