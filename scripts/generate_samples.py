#!/usr/bin/env python3
"""Generate the six synthetic invoice PDFs used by the demo and e2e script."""

from __future__ import annotations

import random
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

SAMPLES = [
    {
        "file": "01_valid_food.pdf",
        "folio": "FOOD-1001",
        "emisor": "ABC010101AB1",
        "receptor": "XYZ010101XY2",
        "date": "05/11/2026",
        "subtotal": "40.00",
        "iva": "6.40",
        "total": "46.40",
        "category": "FOOD",
        "vendor": "Taqueria El Buen Pastor",
        "description": "Comida de trabajo",
    },
    {
        "file": "02_over_limit_transport.pdf",
        "folio": "TRA-2001",
        "emisor": "TRA010101TR2",
        "receptor": "XYZ010101XY2",
        "date": "04/11/2026",
        "subtotal": "301.72",
        "iva": "48.28",
        "total": "350.00",
        "category": "TRANSPORT",
        "vendor": "Taxi Ejecutivo CDMX",
        "description": "Traslado a cliente",
    },
    {
        "file": "03_duplicate_a.pdf",
        "folio": "DUP-3001",
        "emisor": "DUP010101AB1",
        "receptor": "XYZ010101XY2",
        "date": "03/11/2026",
        "subtotal": "103.45",
        "iva": "16.55",
        "total": "120.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Licencia mensual",
    },
    {
        "file": "04_duplicate_b.pdf",
        "folio": "DUP-3001",
        "emisor": "DUP010101AB1",
        "receptor": "XYZ010101XY2",
        "date": "03/11/2026",
        "subtotal": "103.45",
        "iva": "16.55",
        "total": "120.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Licencia mensual",
    },
    {
        "file": "05_invalid_rfc.pdf",
        "folio": "OTH-4001",
        "emisor": "INVALIDO123",
        "receptor": "XYZ010101XY2",
        "date": "02/11/2026",
        "subtotal": "68.97",
        "iva": "11.03",
        "total": "80.00",
        "category": "OTHER",
        "vendor": "Papeleria Central",
        "description": "Material de oficina",
    },
    {
        "file": "06_noisy_scan.pdf",
        "folio": "NOI-5001",
        "emisor": "NOI010101NO1",
        "receptor": "XYZ010101XY2",
        "date": "01/11/2026",
        "subtotal": "25.86",
        "iva": "4.14",
        "total": "30.00",
        "category": "FOOD",
        "vendor": "Cafeteria La Esquina",
        "description": "Cafe y pan",
        "noisy": True,
    },
]


def draw_noise(c: canvas.Canvas, width: float, height: float) -> None:
    random.seed(11)
    c.saveState()
    c.setStrokeGray(0.82)
    c.setFillGray(0.94)
    for x in range(0, int(width), 26):
        c.rect(x, 0, 9, height, fill=1, stroke=0)
    c.setStrokeGray(0.7)
    for y in range(30, int(height), 47):
        c.line(0, y, width, y)
    for _ in range(120):
        x = random.uniform(0, width)
        y = random.uniform(0, height)
        c.setFillGray(random.uniform(0.75, 0.9))
        c.circle(x, y, random.uniform(0.6, 2.2), fill=1, stroke=0)
    c.setStrokeGray(0.35)
    c.rect(24, 24, width - 48, height - 48, fill=0, stroke=1)
    c.restoreState()


def draw_invoice(sample: dict) -> Path:
    path = SAMPLES_DIR / sample["file"]
    width, height = letter
    c = canvas.Canvas(str(path), pagesize=letter)

    if sample.get("noisy"):
        draw_noise(c, width, height)

    left = 60
    y = height - 80
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, "FACTURA")
    c.setFont("Helvetica", 10)
    y -= 22
    c.drawString(left, y, f"Folio: {sample['folio']}")
    y -= 14
    c.drawString(left, y, "RFC Emisor: " + sample["emisor"])
    y -= 14
    c.drawString(left, y, "RFC Receptor: " + sample["receptor"])
    y -= 14
    c.drawString(left, y, "Fecha: " + sample["date"])
    y -= 26
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Proveedor")
    c.setFont("Helvetica", 11)
    c.drawString(left + 110, y, sample["vendor"])
    y -= 16
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Descripcion")
    c.setFont("Helvetica", 11)
    c.drawString(left + 110, y, sample["description"])
    y -= 16
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Categoria")
    c.setFont("Helvetica", 11)
    c.drawString(left + 110, y, sample["category"])

    y -= 34
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Subtotal")
    c.drawRightString(width - 70, y, "$ " + sample["subtotal"])
    y -= 16
    c.drawString(left, y, "IVA")
    c.drawRightString(width - 70, y, "$ " + sample["iva"])
    y -= 16
    c.drawString(left, y, "Total")
    c.drawRightString(width - 70, y, "$ " + sample["total"])

    y -= 40
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(left, y, "Documento sintetico para demo. No es una factura fiscal real.")

    c.showPage()
    c.save()
    return path


def main() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        path = draw_invoice(sample)
        print(f"generated {path.name}")


if __name__ == "__main__":
    main()
