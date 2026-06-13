"""Lecture des fiches de specs internes (PDF, Excel, CSV, TXT)."""
import os
import csv
import json
from pathlib import Path

SPECS_DIR = Path("data/specs")


def find_vehicle_in_files(year: int, make: str, model: str) -> dict | None:
    """Cherche un véhicule dans tous les fichiers du dossier data/specs/."""
    if not SPECS_DIR.exists():
        return None

    make_lower = make.lower().strip()
    model_lower = model.lower().strip()

    for filepath in SPECS_DIR.iterdir():
        ext = filepath.suffix.lower()
        try:
            if ext == ".pdf":
                result = _search_pdf(filepath, year, make_lower, model_lower)
            elif ext in (".xlsx", ".xls"):
                result = _search_excel(filepath, year, make_lower, model_lower)
            elif ext == ".csv":
                result = _search_csv(filepath, year, make_lower, model_lower)
            elif ext in (".txt", ".json"):
                result = _search_text(filepath, year, make_lower, model_lower)
            else:
                continue

            if result:
                result["source_file"] = filepath.name
                return result
        except Exception:
            continue

    return None


def _search_pdf(filepath: Path, year: int, make: str, model: str) -> dict | None:
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            full_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
        if make in full_text.lower() and model in full_text.lower():
            if str(year) in full_text:
                return {"raw_text": full_text, "source_type": "file_pdf"}
    except Exception:
        pass
    return None


def _search_excel(filepath: Path, year: int, make: str, model: str) -> dict | None:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, data_only=True)
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            headers = [str(c).lower() if c else "" for c in (rows[0] if rows else [])]
            for row in rows[1:]:
                row_str = " ".join(str(c).lower() for c in row if c)
                if make in row_str and model in row_str and str(year) in row_str:
                    specs = {}
                    for i, val in enumerate(row):
                        if i < len(headers) and headers[i] and val is not None:
                            specs[headers[i]] = str(val)
                    return {"specs": specs, "source_type": "file_excel"}
    except Exception:
        pass
    return None


def _search_csv(filepath: Path, year: int, make: str, model: str) -> dict | None:
    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_str = " ".join(str(v).lower() for v in row.values())
                if make in row_str and model in row_str and str(year) in row_str:
                    return {"specs": dict(row), "source_type": "file_csv"}
    except Exception:
        pass
    return None


def _search_text(filepath: Path, year: int, make: str, model: str) -> dict | None:
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        if make in content.lower() and model in content.lower() and str(year) in content:
            if filepath.suffix == ".json":
                data = json.loads(content)
                return {"specs": data, "source_type": "file_json"}
            return {"raw_text": content, "source_type": "file_txt"}
    except Exception:
        pass
    return None
