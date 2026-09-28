"""Build synthetic PDF fixtures without a runtime PDF-generation dependency."""
import json
from pathlib import Path

ROOT = Path(__file__).parent


def write_pdf(name, objects):
    pdf, offsets = b"%PDF-1.4\n", [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    pdf += f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    (ROOT / name).write_bytes(pdf)


def text_pdf(name, lines):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    document = canvas.Canvas(str(ROOT / name), pagesize=(595, 842), pageCompression=1)
    document.setTitle(lines[0])
    document.setFillColorRGB(.08, .25, .35)
    document.rect(0, 744, 595, 98, fill=1, stroke=0)
    document.setFillColorRGB(1, 1, 1)
    document.setFont('Helvetica-Bold', 14)
    document.drawString(42, 793, lines[0])
    document.setFont('Helvetica', 10)
    document.drawString(42, 769, 'PERSONAL HEALTH DEMO / SYNTHETIC SOURCE DOCUMENT')
    document.setFillColorRGB(.16, .20, .24)
    document.setFont('Helvetica', 11)
    y = 710
    for line in lines[1:]:
        wrapped = simpleSplit(line, 'Helvetica', 11, 510) or ['']
        for part in wrapped:
            document.drawString(42, y, part)
            y -= 22
        y -= 5
    document.setStrokeColorRGB(.82, .87, .90)
    document.line(42, 73, 553, 73)
    document.setFont('Helvetica', 9)
    document.setFillColorRGB(.38, .44, .48)
    document.drawString(42, 55, 'Synthetic data. Not a real patient record or treatment recommendation.')
    document.drawRightString(553, 37, '1 / 1')
    document.save()


rows = []
for i, (day, bp, glucose, pulse) in enumerate([("2026-06-20", "142/90", "6.2", "82"), ("2026-07-20", "134/84", "5.9", "76"), ("2026-09-20", "126/80", "5.5", "72")], 1):
    filename = f"check-up-{day}.pdf"
    text_pdf(filename, ["DEMONSTRATION HOSPITAL - CHECK-UP REPORT", "Synthetic data for software testing only", "Patient: DEMO OWNER", f"Report date: {day}", f"Measurement date: {day} 08:00", f"Blood pressure: {bp} mmHg", f"Fasting blood glucose: {glucose} mmol/L", f"Resting heart rate: {pulse} bpm", "Clinical note: discuss these measurements at the next review."])
    rows.append({"external_id": f"hospital-lab-{i}", "title": f"{day} 体检与检验报告", "record_type": "Lab Report", "condition": "血压与血糖复查", "record_date": day, "filename": filename, "content": "模拟医院体检报告。原始测量结果保存在 PDF 中；确认后可纳入个人指标。"})

documents = [
    ("visit", "2026-09-20 门诊病历", "Visit Summary", "高血压随访", ["OUTPATIENT VISIT SUMMARY", "Confirmed diagnosis: Hypertension", "Past medical history: Hypertension diagnosed in 2025.", "Family history: Type 2 diabetes | relationship: Father", "Plan: record home readings and discuss follow-up with a clinician."]),
    ("medication", "2026-09-20 用药记录", "Medication", "用药核对", ["MEDICATION RECORD", "Current medication: Amlodipine | dose: 5 mg | frequency: once daily", "This is a synthetic historical medication record, not prescribing advice.", "Bring the medicine list to the next appointment for reconciliation."]),
    ("allergy", "2026-09-20 过敏记录", "Allergy", "青霉素过敏", ["ALLERGY RECORD", "Confirmed allergy: Penicillin | reaction: rash", "Record this reported reaction for discussion with care staff."]),
    ("imaging", "2026-09-20 超声检查报告", "Imaging", "甲状腺检查", ["ULTRASOUND IMAGING REPORT", "Examination: Thyroid ultrasound.", "Finding: A small thyroid nodule is described for follow-up.", "This finding is not a confirmed diagnosis of cancer.", "Ask the treating clinician about the appropriate follow-up plan."]),
]
for key, title, kind, condition, lines in documents:
    filename = key + "-2026-09-20.pdf"
    text_pdf(filename, ["DEMONSTRATION HOSPITAL", "Synthetic data for software testing only", "Patient: DEMO OWNER", "Report date: 2026-09-20", ""] + lines)
    rows.append({"external_id": "hospital-" + key, "title": title, "record_type": kind, "condition": condition, "record_date": "2026-09-20", "filename": filename, "content": "模拟医院原始资料。详情请查看 PDF；个人整理信息与原件分别保存。"})

jpeg = (ROOT / "scanned-care.jpg").read_bytes()
stream = b"q 560 0 0 400 18 380 cm /Im0 Do Q"
write_pdf("scanned-care-2026-09-20.pdf", [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>",
    b"<< /Type /XObject /Subtype /Image /Width 1400 /Height 1000 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length " + str(len(jpeg)).encode() + b" >>\nstream\n" + jpeg + b"\nendstream",
    b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"])
rows.append({"external_id": "hospital-care", "title": "2026-09-20 康复护理扫描记录", "record_type": "Other", "condition": "跟腱康复", "record_date": "2026-09-20", "filename": "scanned-care-2026-09-20.pdf", "content": "模拟医院扫描护理记录。全文搜索依赖本地 OCR 识别结果。"})
# The checked-in manifest owns the bilingual display metadata; rebuilding PDF bytes
# must not replace it with legacy Chinese-only labels.
manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
assert {row["external_id"] for row in rows} == {row["external_id"] for row in manifest}

