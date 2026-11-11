#!/usr/bin/env python3
"""Generate the synthetic invoices used by the demo, e2e script, and scenarios."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
SCENARIOS_DIR = SAMPLES_DIR / "scenarios"
MONTHLY_DIR = SCENARIOS_DIR / "monthly_budget"

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

# Independent scenarios: each can be uploaded on its own, in any order.
SCENARIOS = [
    {
        "file": "01_total_mismatch.pdf",
        "folio": "SCN-1001",
        "emisor": "MIS010101MI1",
        "receptor": "XYZ010101XY2",
        "date": "06/11/2026",
        "subtotal": "100.00",
        "iva": "16.00",
        "total": "120.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Licencia con importes inconsistentes",
    },
    {
        "file": "02_future_date.pdf",
        "folio": "SCN-1002",
        "emisor": "FUT010101FU1",
        "receptor": "XYZ010101XY2",
        "date": "31/12/2035",
        "subtotal": "86.21",
        "iva": "13.79",
        "total": "100.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Licencia prepagada",
    },
    {
        "file": "03_invalid_amount.pdf",
        "folio": "SCN-1003",
        "emisor": "NEG010101NE1",
        "receptor": "XYZ010101XY2",
        "date": "06/11/2026",
        "subtotal": "-43.10",
        "iva": "-6.90",
        "total": "-50.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Nota de credito",
    },
    {
        "file": "04_currency_usd.pdf",
        "folio": "SCN-1004",
        "emisor": "USD010101US1",
        "receptor": "XYZ010101XY2",
        "date": "06/11/2026",
        "subtotal": "86.21",
        "iva": "13.79",
        "total": "100.00",
        "currency": "USD",
        "category": "SOFTWARE",
        "vendor": "CloudTools Inc",
        "description": "Licencia en dolares",
    },
    {
        "file": "05_receptor_other.pdf",
        "folio": "SCN-1005",
        "emisor": "RCO010101RC1",
        "receptor": "ABC010101AB1",
        "date": "07/11/2026",
        "subtotal": "40.00",
        "iva": "6.40",
        "total": "46.40",
        "category": "FOOD",
        "vendor": "Taqueria El Buen Pastor",
        "description": "Comida con receptor distinto",
    },
    {
        "file": "06_missing_fields.pdf",
        "folio": "SCN-1006",
        "emisor": "MIS010101MI2",
        "receptor": None,
        "date": None,
        "subtotal": "68.97",
        "iva": "11.03",
        "total": "80.00",
        "category": "OTHER",
        "vendor": "Papeleria Central",
        "description": "Ticket sin receptor ni fecha",
    },
    {
        "file": "07_tolerance_exact.pdf",
        "folio": "SCN-1007",
        "emisor": "TOL010101TO1",
        "receptor": "XYZ010101XY2",
        "date": "06/11/2026",
        "subtotal": "100.00",
        "iva": "16.00",
        "total": "117.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Diferencia de redondeo aceptada",
    },
    {
        "file": "08_tolerance_mismatch.pdf",
        "folio": "SCN-1008",
        "emisor": "TOL010101TO2",
        "receptor": "XYZ010101XY2",
        "date": "06/11/2026",
        "subtotal": "100.00",
        "iva": "16.00",
        "total": "117.01",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Diferencia de redondeo fuera de tolerancia",
    },
    {
        "file": "09_valid_lodging.pdf",
        "folio": "SCN-1009",
        "emisor": "HOT010101HO1",
        "receptor": "XYZ010101XY2",
        "date": "08/11/2026",
        "subtotal": "215.52",
        "iva": "34.48",
        "total": "250.00",
        "category": "LODGING",
        "vendor": "Hotel Centro",
        "description": "Hospedaje de una noche",
    },
    {
        "file": "10_valid_software.pdf",
        "folio": "SCN-1010",
        "emisor": "SFT010101SF1",
        "receptor": "XYZ010101XY2",
        "date": "09/11/2026",
        "subtotal": "258.62",
        "iva": "41.38",
        "total": "300.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Licencia anual",
    },
    {
        "file": "11_valid_transport.pdf",
        "folio": "SCN-1011",
        "emisor": "TRV010101TR1",
        "receptor": "XYZ010101XY2",
        "date": "10/11/2026",
        "subtotal": "129.31",
        "iva": "20.69",
        "total": "150.00",
        "category": "TRANSPORT",
        "vendor": "Taxi Ejecutivo CDMX",
        "description": "Traslado al aeropuerto",
    },
    {
        "file": "12_valid_other.pdf",
        "folio": "SCN-1012",
        "emisor": "PAP010101PA1",
        "receptor": "XYZ010101XY2",
        "date": "10/11/2026",
        "subtotal": "68.97",
        "iva": "11.03",
        "total": "80.00",
        "category": "OTHER",
        "vendor": "Papeleria Central",
        "description": "Material de oficina",
    },
    {
        "file": "13_iva_missing.pdf",
        "folio": "SCN-1013",
        "emisor": "SIN010101SI1",
        "receptor": "XYZ010101XY2",
        "date": "10/11/2026",
        "subtotal": "100.00",
        "iva": None,
        "total": "100.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Licencia sin IVA desglosado",
    },
]

# Upload in filename order on a clean expenses table. The first six hit the
# SOFTWARE per-expense limit exactly; the seventh exceeds the monthly budget.
MONTHLY_SCENARIOS = [
    {
        "file": f"{index:02d}_software_500_{suffix}.pdf",
        "folio": f"MB-{index:02d}",
        "emisor": f"MB{letter}010101MB{index}",
        "receptor": "XYZ010101XY2",
        "date": f"{index:02d}/11/2026",
        "subtotal": "431.03",
        "iva": "68.97",
        "total": "500.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Licencia mensual",
    }
    for index, (letter, suffix) in enumerate(
        zip("ABCDEF", ["a", "b", "c", "d", "e", "f"], strict=True), start=1
    )
]
MONTHLY_SCENARIOS.append(
    {
        "file": "07_software_100_over_budget.pdf",
        "folio": "MB-07",
        "emisor": "MBG010101MB7",
        "receptor": "XYZ010101XY2",
        "date": "10/11/2026",
        "subtotal": "86.21",
        "iva": "13.79",
        "total": "100.00",
        "category": "SOFTWARE",
        "vendor": "CloudTools SA de CV",
        "description": "Licencia adicional que excede el presupuesto",
    }
)


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


def draw_invoice(sample: dict, directory: Path) -> Path:
    path = directory / sample["file"]
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
    if sample.get("receptor"):
        c.drawString(left, y, "RFC Receptor: " + sample["receptor"])
        y -= 14
    if sample.get("date"):
        c.drawString(left, y, "Fecha: " + sample["date"])
        y -= 14
    if sample.get("currency"):
        c.drawString(left, y, "Moneda: " + sample["currency"])
        y -= 14

    y -= 12
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
    if sample.get("iva") is not None:
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


def generate(samples: list[dict], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        path = draw_invoice(sample, directory)
        print(f"generated {path.relative_to(SAMPLES_DIR.parent)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios-only",
        action="store_true",
        help="generate only the scenario pack, leaving the six core samples untouched",
    )
    args = parser.parse_args()

    if not args.scenarios_only:
        generate(SAMPLES, SAMPLES_DIR)
    generate(SCENARIOS, SCENARIOS_DIR)
    generate(MONTHLY_SCENARIOS, MONTHLY_DIR)


if __name__ == "__main__":
    main()
