"""Build tiny CV files in memory, so tests do not need binary fixtures."""

import io


def make_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with one text line per entry. Latin-1 characters only."""

    def escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = ["BT", "/F1 11 Tf", "14 TL", "72 760 Td"]
    content += [f"({escape(line)}) Tj T*" for line in lines]
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objects) + 1,
        xref_at,
    )
    return bytes(out)


def make_docx(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


SAMPLE_CV = [
    "JOHN DOE",
    "Backend developer",
    "",
    "EXPERIENCE",
    "Built a FastAPI service deployed with Docker Compose.",
    "Reduced latency by 40% using caching.",
    "",
    "EDUCATION",
    "MSc Computer Science, University of Trento",
    "",
    "SKILLS",
    "Python, SQL, Docker, pytest",
]
