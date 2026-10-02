"""Rebuild committed, fictional single-page packets. Run from repository root."""

from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor

# Samples ship inside the backend package so Lambda bundles include them.
ROOT = Path(__file__).resolve().parents[1] / "backend" / "app" / "samples"
TYPES = ("client_profile", "transfer_application", "account_statement")


def write_pdf(path: Path, kind: str, fields: dict[str, str]) -> None:
    """Draw one fictional single-page form with "Label: value" lines."""
    pdf = Canvas(str(path), pagesize=(612, 792), invariant=1)
    pdf.setTitle("ClearPath synthetic sample — " + kind.replace("_", " "))
    pdf.setFillColor(HexColor("#173c44"))
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawString(48, 736, "ClearPath / Synthetic sample")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(48, 690, kind.replace("_", " ").title())
    pdf.setFont("Helvetica", 11)
    pdf.drawString(
        48,
        657,
        "Fictional data. Not an LPL form. Not for real account processing.",
    )
    y = 600
    for label, value in fields.items():
        pdf.drawString(48, y, f"{label}: {value}")
        y -= 38
    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        48,
        72,
        "Hackathon sample policy only. This packet does not establish compliance.",
    )
    pdf.save()


def generate():
    for packet in ("complete", "missing", "conflicting", "formatting"):
        folder = ROOT / packet
        folder.mkdir(parents=True, exist_ok=True)
        for kind in TYPES:
            fields = {
                "Client Name": "Jordan Example",
                "Address": "100 Fictional Lane, Demo City, NY 00000",
            }
            if kind != "account_statement":
                fields["SSN"] = "000-12-3456"
            if kind != "client_profile":
                fields["Account Number"] = "DEMO-10001234"
            if kind == "transfer_application":
                fields["Receiving Account"] = "RECV-50005678"
                if packet == "missing":
                    fields["Receiving Account"] = ""
                    fields["Address"] = ""
                if packet == "formatting":
                    # Same address, abbreviated: a classic false alarm.
                    fields["Address"] = "100 Fictional Ln, Demo City, NY 00000"
                if packet == "conflicting":
                    fields.update(
                        SSN="000-98-7654",
                        Address="200 Imaginary Road, Demo City, NY 00000",
                    )
                    fields["Account Number"] = "DEMO-90004321"
            write_pdf(folder / f"{kind}.pdf", kind, fields)


if __name__ == "__main__":
    generate()