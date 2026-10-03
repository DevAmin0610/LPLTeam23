import { useEffect, useState } from "react";
import type { CaseDocument, Evidence } from "./types";
import { api, errorMessage } from "./api";
import { documentLabel } from "./types";

interface PdfViewerProps {
  caseId: string;
  documents: CaseDocument[];
  evidence: Evidence | null;
  onSelectEvidence: (ev: Evidence) => void;
}

export default function PdfViewer({
  caseId,
  documents,
  evidence,
  onSelectEvidence,
}: PdfViewerProps) {
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState("");

  const activeDocId = evidence?.document_id ?? documents[0]?.id;
  const doc = documents.find((item) => item.id === activeDocId) ?? documents[0];
  const docId = doc?.id;
  const currentPage =
    evidence?.document_id === docId ? (evidence?.page ?? 1) : page;

  useEffect(() => {
    if (!docId) {
      setPdfUrl(null);
      return;
    }
    const controller = new AbortController();
    let active = true;
    let objectUrl: string | null = null;
    setLoading(true);
    setPdfError("");
    setPdfUrl(null);
    void api
      .documentPdf(caseId, docId, controller.signal)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
      })
      .catch((error: unknown) => {
        if (
          active &&
          !(error instanceof DOMException && error.name === "AbortError")
        ) {
          setPdfError(errorMessage(error));
          setLoading(false);
        }
      });
    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [caseId, docId]);

  function selectDoc(selected: CaseDocument) {
    setPage(1);
    setLoading(true);
    onSelectEvidence({
      document_id: selected.id,
      page: 1,
      excerpt: "",
      bounding_box: null,
    });
  }

  function goToPage(next: number) {
    setPage(next);
    setLoading(true);
    if (doc)
      onSelectEvidence({
        document_id: doc.id,
        page: next,
        excerpt:
          evidence?.document_id === doc.id ? (evidence?.excerpt ?? "") : "",
        bounding_box: null,
      });
  }

  if (!doc) {
    return <div className="empty">Upload a document to view it here.</div>;
  }

  const src = pdfUrl ? `${pdfUrl}#page=${currentPage}` : undefined;

  return (
    <div className="pdf-viewer">
      <div className="tabs">
        {documents.map((item) => (
          <button
            key={item.id}
            className={doc.id === item.id ? "selected" : ""}
            onClick={() => selectDoc(item)}
          >
            {documentLabel(item.document_type)}
          </button>
        ))}
      </div>
      <div className="viewer-meta">
        <span>Original synthetic document · page {currentPage}</span>
        {pdfUrl && (
          <a href={pdfUrl} target="_blank" rel="noreferrer">
            Open PDF ↗
          </a>
        )}
      </div>
      <div className="pdf-frame-wrap">
        {loading && (
          <div className="pdf-loading" aria-live="polite">
            Loading…
          </div>
        )}
        {pdfError && (
          <div role="alert" className="error">
            {pdfError}
          </div>
        )}
        {src && (
          <iframe
            key={`${doc.id}:${currentPage}`}
            title={documentLabel(doc.document_type)}
            src={src}
            onLoad={() => setLoading(false)}
          />
        )}
      </div>
      <div className="pdf-controls">
        <button
          disabled={currentPage <= 1}
          onClick={() => goToPage(currentPage - 1)}
          aria-label="Previous page"
        >
          ← Prev
        </button>
        <span className="pdf-page-label">Page {currentPage}</span>
        <button
          onClick={() => goToPage(currentPage + 1)}
          aria-label="Next page"
        >
          Next →
        </button>
      </div>
      {evidence?.document_id === doc.id && evidence.excerpt && (
        <div className="excerpt">
          <strong>Sanitized source reference</strong>
          <p>{evidence.excerpt}</p>
          <small>
            Page navigation only. Local extraction does not provide reliable
            bounding boxes.
          </small>
        </div>
      )}
    </div>
  );
}
