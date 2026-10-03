import { useState } from "react";
import type { CaseDocument, Evidence } from "./types";
import { documentUrl } from "./api";
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

  const activeDocId = evidence?.document_id ?? documents[0]?.id;
  const doc = documents.find((d) => d.id === activeDocId) ?? documents[0];
  const currentPage = evidence?.document_id === doc?.id ? (evidence?.page ?? 1) : page;

  function selectDoc(d: CaseDocument) {
    setPage(1);
    setLoading(true);
    onSelectEvidence({ document_id: d.id, page: 1, excerpt: "", bounding_box: null });
  }

  function goToPage(next: number) {
    setPage(next);
    setLoading(true);
    if (doc)
      onSelectEvidence({
        document_id: doc.id,
        page: next,
        excerpt: evidence?.document_id === doc.id ? (evidence?.excerpt ?? "") : "",
        bounding_box: null,
      });
  }

  if (!doc) {
    return <div className="empty">Upload a document to view it here.</div>;
  }

  const src = `${documentUrl(caseId, doc.id)}#page=${currentPage}`;

  return (
    <div className="pdf-viewer">
      <div className="tabs">
        {documents.map((d) => (
          <button
            key={d.id}
            className={doc.id === d.id ? "selected" : ""}
            onClick={() => selectDoc(d)}
          >
            {documentLabel(d.document_type)}
          </button>
        ))}
      </div>
      <div className="viewer-meta">
        <span>
          Original synthetic document · page {currentPage}
        </span>
        <a href={documentUrl(caseId, doc.id)} target="_blank" rel="noreferrer">
          Open PDF ↗
        </a>
      </div>
      <div className="pdf-frame-wrap">
        {loading && <div className="pdf-loading" aria-live="polite">Loading…</div>}
        <iframe
          key={`${doc.id}:${currentPage}`}
          title={documentLabel(doc.document_type)}
          src={src}
          onLoad={() => setLoading(false)}
        />
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
