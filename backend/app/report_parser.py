"""Local report text extraction and conservative candidate recognition; no diagnosis."""
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from functools import lru_cache

from pypdf import PdfReader

MAX_PAGES = 5
MAX_TEXT = 60000
OCR_TIMEOUT = 35
SCRIPT = Path(__file__).with_name("windows_ocr.ps1")


def _powershell(*arguments, timeout=OCR_TIMEOUT):
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(SCRIPT), *arguments], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


@lru_cache(maxsize=1)
def ocr_capabilities():
    if os.name != "nt":
        return {"available": False, "languages": [], "engine": "Windows OCR", "reason": "Windows OCR is not available on this server. Paste report text instead."}
    try:
        result = _powershell("-Capabilities", timeout=8)
        payload = json.loads(result.stdout.lstrip("\ufeff"))
        if result.returncode == 0:
            return payload
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {"available": False, "languages": [], "engine": "Windows OCR", "reason": "Local OCR could not start. Paste report text instead."}


def windows_ocr(data, extension, pages=None, language="auto"):
    if not ocr_capabilities().get("available"):
        return {}, "Local image OCR is unavailable. Paste the report text to continue."
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temporary:
            temporary.write(data)
            path = temporary.name
        result = _powershell("-InputPath", path, "-Language", language,
            "-PageNumbers", ",".join(str(page) for page in (pages or [])))
        payload = json.loads(result.stdout.lstrip("\ufeff"))
        if result.returncode or payload.get("error"):
            return {}, "Local OCR could not read this file. Try a clearer image, another installed language, or paste the text."
        return {page["page"]: page["text"] for page in payload.get("pages", [])}, None
    except subprocess.TimeoutExpired:
        return {}, f"Local OCR stopped after {OCR_TIMEOUT} seconds. Paste the text or upload fewer, clearer pages."
    except (OSError, ValueError):
        return {}, "Local OCR could not start. Paste the report text to continue."
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


def extract_attachment(data, content_type, language="auto"):
    warnings, text_pages = [], {}
    total_pages = 1
    method = "windows_ocr"
    processed = []
    if content_type == "application/pdf":
        method = "pdf_text"
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                return {"text": "", "method": "unreadable_pdf", "warnings": ["This PDF is password protected. Upload an unlocked copy or paste its text."], "total_pages": None, "processed_pages": []}
            total_pages = len(reader.pages)
            for index in range(min(MAX_PAGES, total_pages)):
                try:
                    text_pages[index + 1] = (reader.pages[index].extract_text() or "")[:MAX_TEXT]
                except Exception:
                    text_pages[index + 1] = ""
        except Exception:
            return {"text": "", "method": "unreadable_pdf", "warnings": ["This PDF could not be opened. Upload another copy or paste its text."], "total_pages": None, "processed_pages": []}
        missing = [page for page, text in text_pages.items() if not text.strip()]
        processed = [page for page, text in text_pages.items() if text.strip()]
        if missing:
            ocr_pages, warning = windows_ocr(data, ".pdf", missing, language)
            text_pages.update(ocr_pages)
            processed += [page for page, text in ocr_pages.items() if text.strip()]
            if ocr_pages:
                method = "pdf_text_and_windows_ocr" if any(page not in missing for page in text_pages) else "windows_ocr"
            if warning:
                warnings.append(warning)
        if total_pages > MAX_PAGES:
            warnings.append(f"Only the first {MAX_PAGES} of {total_pages} pages were processed. {total_pages - MAX_PAGES} later pages were not processed; split the report or paste their text separately.")
    else:
        extension = ".png" if content_type == "image/png" else ".jpg"
        text_pages, warning = windows_ocr(data, extension, language=language)
        processed = [page for page, text in text_pages.items() if text.strip()]
        if warning:
            warnings.append(warning)
    text = "\n\n".join(f"[Page {page}]\n{text}" for page, text in sorted(text_pages.items()) if text.strip())
    if len(text) > MAX_TEXT:
        warnings.append(f"Text was limited to {MAX_TEXT:,} characters. Remaining text was not processed.")
        text = text[:MAX_TEXT]
    unread = [page for page in range(1, min(total_pages, MAX_PAGES) + 1) if page not in processed]
    if unread:
        warnings.append("No usable text was read on page(s) " + ", ".join(map(str, unread)) + ".")
    warnings.append("Review the text against the original report. Extraction can misread values, labels, units or columns.")
    return {"text": text, "method": method, "warnings": warnings,
            "total_pages": total_pages, "processed_pages": sorted(set(processed))}


def extract_document(data, content_type, language="auto"):
    """Index all document pages; OCR is batched, incomplete work is never 'complete'."""
    pages, warnings, total_pages = [], [], 1
    started = time.monotonic()
    if content_type != "application/pdf":
        text_pages, error = windows_ocr(data, ".png" if content_type == "image/png" else ".jpg", language=language)
        pages = [{"page": number, "text": text, "method": "windows_ocr"} for number, text in sorted(text_pages.items())]
        if error:
            warnings.append(error)
    else:
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("encrypted")
            total_pages = len(reader.pages)
            # Bound resource use, but expose every unprocessed page to the user.
            limit = min(total_pages, 200)
            if limit < total_pages:
                warnings.append(f"文档共有 {total_pages} 页，本次最多处理 200 页；请拆分后续页面继续整理。")
            for number in range(1, limit + 1):
                try:
                    text = reader.pages[number - 1].extract_text() or ""
                except Exception:
                    text = ""
                pages.append({"page": number, "text": text, "method": "pdf_text"})
            missing = [p["page"] for p in pages if not p["text"].strip()]
            for offset in range(0, len(missing), MAX_PAGES):
                if time.monotonic() - started > 110:
                    warnings.append("本次 OCR 已达到处理时间限制；尚未识别的页面不会出现在全文搜索中，请拆分后重试。")
                    break
                batch = missing[offset:offset + MAX_PAGES]
                texts, error = windows_ocr(data, ".pdf", batch, language)
                for page in pages:
                    if page["page"] in texts:
                        page.update(text=texts[page["page"]], method="windows_ocr")
                if error:
                    warnings.append(error)
                    if not ocr_capabilities().get("available"):
                        break
        except Exception:
            return {"pages": [], "status": "failed", "total_pages": None,
                    "warnings": ["无法打开 PDF，文件可能损坏或受密码保护。原文件仍已保存，可重新上传可读副本。"]}
    count = sum(bool(p["text"].strip()) for p in pages)
    if count < total_pages:
        warnings.append(f"已识别 {count}/{total_pages} 页。未识别页暂时无法全文检索，请查看原件并重试。")
    return {"pages": pages, "status": "complete" if count == total_pages and total_pages else "partial" if count else "failed",
            "total_pages": total_pages, "warnings": list(dict.fromkeys(warnings))}


LABEL_BOUNDARY = r"(?<![A-Za-z\u4e00-\u9fff])"
PATTERNS = [
    ("blood_pressure", re.compile(LABEL_BOUNDARY + r"(?:blood\s+pressure|bp|血压)\s*[:：=]?\s*(?P<value>\d{2,3})\s*[/／]\s*(?P<secondary>\d{2,3})\s*(?P<unit>mm\s*hg|毫米汞柱)(?![A-Za-z])", re.I)),
    ("blood_glucose", re.compile(LABEL_BOUNDARY + r"(?P<label>(?:fasting\s+)?(?:blood\s+)?glucose|blood\s+sugar|fpg|fbg|空腹血糖|餐后血糖|血糖)\s*[:：=]?\s*(?P<value>\d{1,3}(?:\.\d+)?)\s*(?P<unit>mmol\s*[/／]\s*l|mg\s*[/／]\s*dl)(?![A-Za-z])", re.I)),
    ("heart_rate", re.compile(LABEL_BOUNDARY + r"(?P<label>(?:resting\s+)?heart\s+rate|pulse|hr|静息心率|心率|脉搏)\s*[:：=]?\s*(?P<value>\d{2,3})\s*(?P<unit>bpm|beats\s*/\s*min(?:ute)?|次\s*[/／]\s*分(?:钟)?)(?![A-Za-z])", re.I)),
]
REFERENCE_LINE = re.compile(r"\breference\b|\btarget\b|\brange\b|\bexample\b|参考|目标|正常范围|示例", re.I)


def parse_candidates(text):
    candidates, occurrences = [], {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if REFERENCE_LINE.search(line):
            continue
        for metric, pattern in PATTERNS:
            for match in pattern.finditer(line):
                unit = match.group("unit").lower().replace(" ", "").replace("／", "/")
                unit = "mmHg" if metric == "blood_pressure" else "bpm" if metric == "heart_rate" else "mg/dL" if unit == "mg/dl" else "mmol/L"
                label = match.groupdict().get("label", "").casefold()
                context = "fasting" if metric == "blood_glucose" and ("fasting" in label or label in {"fpg", "fbg", "空腹血糖"}) else "after_meal" if "餐后" in label else "resting" if "resting" in label or "静息" in label else "unknown" if metric == "heart_rate" else ""
                evidence = match.group(0)
                signature = f"{metric}|{evidence.casefold().strip()}"
                ordinal = occurrences.get(signature, 0)
                occurrences[signature] = ordinal + 1
                key = hashlib.sha256(f"{signature}|{ordinal}".encode()).hexdigest()[:24]
                candidates.append({"id": key, "metric_type": metric, "value": float(match.group("value")),
                    "secondary_value": float(match.group("secondary")) if metric == "blood_pressure" else None,
                    "unit": unit, "context": context, "measured_at": None,
                    "evidence": evidence, "line_number": line_number,
                    "warning": "Confirm the measurement date/time, value, unit and measurement context before importing."})
                if len(candidates) >= 50:
                    return candidates
    return candidates
