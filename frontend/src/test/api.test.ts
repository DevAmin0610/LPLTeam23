import { describe, expect, it } from "vitest";
import { safePreview, validatePdf } from "../api";

describe("frontend boundaries", () => {
  it("rejects empty and non-PDF selections", () => {
    expect(validatePdf(new File([], "sample.pdf"))).not.toBeNull();
    expect(validatePdf(new File(["text"], "sample.txt"))).not.toBeNull();
    expect(validatePdf(new File(["%PDF-"], "sample.pdf"))).toBeNull();
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
