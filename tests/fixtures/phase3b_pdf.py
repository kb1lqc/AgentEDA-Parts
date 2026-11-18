"""Tiny stdlib PDF writer for the Phase 3b script tests (text pages, image-only pages). Deterministic bytes."""


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(pages, scanned=(), rotate=()):
    """pages: list of lists of (x, y_from_top, size, text). Text is latin-1 (WinAnsi); y measured from the top of a
    612x792 page. scanned: 1-based page numbers that are an image only (no text layer) instead of the text."""
    objs = []  # bytes bodies, object number = index + 1

    def add(b):
        objs.append(b)
        return len(objs)

    add(b"")  # 1 catalog placeholder
    add(b"")  # 2 pages placeholder
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    img = add(b"<< /Type /XObject /Subtype /Image /Width 8 /Height 8 /ColorSpace /DeviceGray /BitsPerComponent 8 "
              b"/Length 64 >>\nstream\n" + bytes(range(0, 256, 4)) + b"\nendstream")
    kids = []
    for n, items in enumerate(pages, 1):
        if n in scanned:
            content = b"q 612 0 0 792 0 0 cm /Im0 Do Q"
        else:
            parts = []
            for x, y, size, text in items:
                parts.append("BT /F1 %g Tf %g %g Td (%s) Tj ET" % (size, x, 792 - y, _esc(text)))
            content = "\n".join(parts).encode("latin-1")
        c = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        p = add(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] %s /Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> "
                 "/XObject << /Im0 %d 0 R >> >> >>" % ("/Rotate 90" if n in rotate else "", c, font, img)).encode())
        kids.append(p)
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % k for k in kids), len(kids))).encode()
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, b in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + b + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def footer(n):
    return (300, 760, 9, str(n))


def datasheet_pages():
    """4 pages: abs max / electrical table / electrical (continued) / pin functions + a second Recommended table."""
    hdr = lambda y: [(40, y, 8, "PARAMETER"), (220, y, 8, "TEST CONDITIONS"), (330, y, 8, "MIN"), (380, y, 8, "TYP"),
                     (430, y, 8, "MAX"), (480, y, 8, "UNIT")]
    p1 = [(40, 80, 14, "6.1 Absolute Maximum Ratings"), (40, 100, 9, "free text line one"),
          (40, 400, 14, "6.3 Recommended Operating Conditions"), (40, 420, 9, "rows"), footer(1)]
    p2 = [(40, 80, 14, "6.5 Electrical Characteristics")] + hdr(110) + [
        (40, 130, 8, "VOS"), (80, 130, 8, "Input offset voltage"), (330, 130, 8, "-"), (380, 130, 8, "10"),
        (430, 130, 8, "35"), (480, 130, 8, "\xb5V"),
        (40, 160, 8, "IB"), (80, 160, 8, "Input bias current"), (380, 160, 8, "0.1"), (430, 160, 8, "0.5"),
        (480, 160, 8, "nA"),
        (40, 190, 8, "VCM"), (80, 190, 8, "Common-mode range"), (330, 190, 8, "\x96" + "0.3"), (430, 190, 8, "85"),
        (480, 190, 8, "V"),
        (40, 220, 8, "AOL"), (80, 220, 8, "Open-loop gain"), (330, 220, 8, "100"), (380, 220, 8, "120(1)"),
        (480, 220, 8, "dB"),
        (40, 250, 8, "IQ"), (80, 250, 8, "Quiescent current"), (380, 250, 8, "1.2"), (430, 250, 8, "2"),
        (480, 250, 8, "mA"),
        (40, 280, 8, "IQ"), (80, 280, 8, "Quiescent current, hot"), (380, 280, 8, "1.4"), (430, 280, 8, "2.5"),
        (480, 280, 8, "mA"),
        (40, 310, 8, "GE"), (80, 310, 8, "Gain error"), (380, 310, 8, "0.01"), (430, 310, 8, "0.05"),
        (480, 310, 8, "%"),
        (40, 340, 8, "VN"), (80, 340, 8, "Noise"), (380, 340, 8, "5"), (480, 340, 8, "nV/rtHz"),
        (40, 370, 8, "WRAP"), (80, 370, 8, "Wrapped name"), (380, 370, 8, "3"), (430, 370, 8, "4"), (480, 370, 8, "V"),
        (80, 380, 8, "second line"),
        (40, 410, 8, "NOUNIT"), (80, 410, 8, "Row with no unit cell"), (380, 410, 8, "7"),
        footer(2)]
    p3 = [(40, 80, 14, "6.5 Electrical Characteristics (continued)"), footer(3)]
    p4 = [(40, 80, 14, "5 Pin Configuration and Functions"), (300, 86, 8, "7"), (320, 86, 8, "Vs"), (40, 100, 10, "Pin Functions"), (40, 120, 8, "NAME"), (120, 120, 8, "NO."),
          (40, 140, 8, "OUT"), (120, 140, 8, "1"), (40, 160, 8, "VCC"), (120, 160, 8, "2"),
          (40, 180, 8, "GND"), (120, 180, 8, "3"),
          (40, 400, 14, "6.3 Recommended Operating Conditions"), footer(4)]
    return [p1, p2, p3, p4]
