from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

INK = (0.11, 0.10, 0.09)
MUTED = (0.35, 0.32, 0.28)
GREEN = (0.12, 0.36, 0.25)
RED = (0.70, 0.25, 0.11)
RULE = (0.78, 0.74, 0.66)
PAPER = (0.96, 0.94, 0.90)
WHITE = (1, 1, 1)

FORM_FIELDS = [
    ("applicant_name", "Applicant full name", "Alex Rivera"),
    ("date_of_birth", "Date of birth", "3 March 1961"),
    ("home_address", "Home address", "14 Example Lane"),
    ("city_postcode", "City and postcode", "Wellington 6011"),
    ("reference_number", "Renewal reference number", "SYN-2048-731"),
    ("renewal_period", "Renewal period", "1 January 2027 to 31 December 2027"),
    ("household_size", "Number of people in your household", ""),
    ("monthly_income", "Monthly income before tax", "NZD 1,840"),
    ("bank_name", "Bank name", "Example Community Bank"),
    ("account_last_four", "Last four digits of account", "4821"),
    ("mailing_same", "Is your mailing address the same?", ""),
    ("monthly_expenses", "Monthly housing costs", "NZD 760"),
    ("witness_name", "Name of witness who knows you", ""),
    ("witness_duration", "How long has the witness known you?", ""),
]

DOCUMENT_ANSWER_KEYS = frozenset(
    {
        "applicant_name",
        "date_of_birth",
        "home_address",
        "city_postcode",
        "reference_number",
        "renewal_period",
        "monthly_income",
        "bank_name",
        "account_last_four",
        "monthly_expenses",
    }
)


def vault_dir() -> Path:
    return DOCS / "vault"


def _save(document, path: Path, title: str):
    document.set_metadata(
        {
            "title": title,
            "author": "Relay demo generator",
            "subject": "Synthetic data for a product demonstration",
        }
    )
    document.save(path, garbage=4, deflate=True)
    document.close()


def _footer(page, text="SYNTHETIC — NOT A REAL DOCUMENT"):
    page.insert_text((46, 760), text, fontsize=8, color=MUTED)


def _letterhead(page, organisation: str, tagline: str):
    page.draw_rect(fitz.Rect(0, 0, 612, 92), color=None, fill=GREEN)
    page.insert_text((46, 54), organisation, fontsize=21, fontname="tiro", color=WHITE)
    page.insert_text((46, 76), tagline, fontsize=9, color=(0.88, 0.92, 0.89))


def _fact_rows(page, rows, x, y, label_width, size=11):
    for label, value in rows:
        page.insert_text((x, y), label.upper(), fontsize=7.5, fontname="hebo", color=MUTED)
        page.insert_text((x, y + 15), value, fontsize=size, color=INK)
        y += 36
    return y


def add_page_heading(page, section, page_number):
    page.insert_text((46, 40), "RENEWAL FORM  /  SYNTHETIC DEMO", fontsize=9, color=MUTED)
    page.draw_line((46, 53), (566, 53), color=RULE, width=0.7)
    page.insert_text((46, 83), "Public Support Renewal", fontsize=22, fontname="tiro", color=INK)
    page.insert_text((46, 107), section, fontsize=12, color=GREEN)
    page.insert_text((46, 760), f"SYNTHETIC — NOT A REAL APPLICATION     {page_number}", fontsize=8, color=MUTED)


def create_form(path: Path):
    document = fitz.open()
    sections = ("Part A — About you", "Part B — Household and income", "Part C — A person who knows you")
    for offset in range(0, len(FORM_FIELDS), 5):
        page_number = offset // 5 + 1
        page = document.new_page(width=612, height=792)
        add_page_heading(page, sections[page_number - 1], page_number)
        if page_number == 1:
            page.insert_text((46, 139), "Please return this renewal by 30 November 2026.", fontsize=11, color=INK)
            page.insert_text((46, 160), "We use your answers to review this renewal. This form does not determine eligibility.", fontsize=9)
            page.insert_textbox(
                fitz.Rect(46, 170, 566, 228),
                "Supporting documents needed: proof of identity, a recent bank statement and your assessment "
                "letter. Your answers for name, date of birth, address, reference, renewal dates, income, bank "
                "details and housing costs should match these documents. Review each answer before returning "
                "this form.",
                fontsize=9,
                color=INK,
            )
        y = 237 if page_number == 1 else 205
        for key, label, _ in FORM_FIELDS[offset : offset + 5]:
            page.insert_text((48, y), label, fontsize=10, color=INK)
            widget = fitz.Widget()
            widget.field_name = key
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_value = ""
            widget.rect = fitz.Rect(48, y + 9, 560, y + 33)
            widget.text_fontsize = 10
            widget.border_width = 0.7
            widget.border_color = (0.55, 0.51, 0.44)
            widget.fill_color = (1, 1, 1)
            page.add_widget(widget)
            y += 92
    _save(document, path, "Synthetic Public Support Renewal")


def create_identity_card(path: Path, answers: dict):
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    _letterhead(page, "Example Identity Office", "Synthetic national identity card")
    card = fitz.Rect(46, 140, 566, 420)
    page.draw_rect(card, color=RULE, fill=(1, 0.99, 0.96), width=1.2)
    page.draw_rect(fitz.Rect(46, 140, 566, 174), color=None, fill=PAPER)
    page.insert_text((64, 162), "IDENTITY CARD  /  SYNTHETIC", fontsize=9, fontname="hebo", color=MUTED)
    photo = fitz.Rect(66, 196, 196, 356)
    page.draw_rect(photo, color=RULE, fill=(0.88, 0.86, 0.81))
    page.draw_circle(fitz.Point(131, 252), 27, color=None, fill=(0.66, 0.63, 0.57))
    page.draw_rect(fitz.Rect(93, 288, 169, 356), color=None, fill=(0.66, 0.63, 0.57))
    page.insert_text((101, 376), "PHOTO PLACEHOLDER", fontsize=7.5, color=MUTED)
    _fact_rows(
        page,
        [
            ("Full name", answers["applicant_name"]),
            ("Date of birth", answers["date_of_birth"]),
            ("Address", answers["home_address"]),
            ("City and postcode", answers["city_postcode"]),
            ("Card number", "SYN-ID-5530-218"),
        ],
        232,
        198,
        200,
        size=13,
    )
    page.draw_line((46, 440), (566, 440), color=RULE, width=0.7)
    page.insert_textbox(
        fitz.Rect(46, 452, 566, 520),
        "Issued 12 June 2022. Valid until 11 June 2032. This card is generated for a product "
        "demonstration and does not identify a real person.",
        fontsize=9.5,
        color=MUTED,
    )
    _footer(page)
    _save(document, path, "Identity card")


def create_assessment_letter(path: Path, answers: dict):
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    _letterhead(page, "Example Services Agency", "Public support assessments")
    page.insert_text((46, 132), "14 October 2026", fontsize=10, color=MUTED)
    page.insert_text((46, 166), answers["applicant_name"], fontsize=11, fontname="hebo", color=INK)
    page.insert_text((46, 182), answers["home_address"], fontsize=11, color=INK)
    page.insert_text((46, 198), answers["city_postcode"], fontsize=11, color=INK)
    page.insert_text((46, 236), "Your assessment outcome", fontsize=16, fontname="tiro", color=INK)
    page.insert_textbox(
        fitz.Rect(46, 248, 566, 308),
        f"Dear {answers['applicant_name']}, we have reviewed your circumstances and your support "
        "continues. The key details are below. Please keep this letter with your other records.",
        fontsize=10.5,
        color=INK,
    )
    panel = fitz.Rect(46, 322, 566, 466)
    page.draw_rect(panel, color=RULE, fill=PAPER, width=1)
    page.draw_rect(fitz.Rect(46, 322, 52, 466), color=None, fill=RED)
    _fact_rows(
        page,
        [
            ("Renewal reference", answers["reference_number"]),
            ("Renewal period", answers["renewal_period"]),
            ("Return your renewal by", "30 November 2026"),
        ],
        70,
        346,
        200,
        size=12,
    )
    page.insert_textbox(
        fitz.Rect(46, 486, 566, 560),
        "If any of these details are wrong, contact us before returning your renewal. We cannot "
        "change them after the return date.",
        fontsize=10.5,
        color=INK,
    )
    page.insert_text((46, 590), "Example Services Agency", fontsize=10, fontname="hebo", color=INK)
    _footer(page)
    _save(document, path, "Assessment letter")


def create_bank_statement(path: Path, answers: dict):
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    _letterhead(page, answers["bank_name"], "Account statement  /  September 2026")
    page.insert_text((46, 132), "ACCOUNT HOLDER", fontsize=7.5, fontname="hebo", color=MUTED)
    page.insert_text((46, 148), answers["applicant_name"], fontsize=12, color=INK)
    page.insert_text((330, 132), "ACCOUNT", fontsize=7.5, fontname="hebo", color=MUTED)
    page.insert_text((330, 148), f"Account ending {answers['account_last_four']}", fontsize=12, color=INK)
    page.draw_rect(fitz.Rect(46, 176, 566, 262), color=RULE, fill=PAPER, width=1)
    page.insert_text((62, 198), "MONTHLY SUMMARY", fontsize=7.5, fontname="hebo", color=MUTED)
    page.insert_text((62, 222), f"Monthly income before tax: {answers['monthly_income']}", fontsize=11, color=INK)
    page.insert_text((62, 244), f"Monthly housing costs: {answers['monthly_expenses']}", fontsize=11, color=INK)

    page.insert_text((46, 300), "Transactions", fontsize=15, fontname="tiro", color=INK)
    top = 314
    page.draw_rect(fitz.Rect(46, top, 566, top + 24), color=None, fill=PAPER)
    for text, x in (("DATE", 56), ("DESCRIPTION", 130)):
        page.insert_text((x, top + 16), text, fontsize=7.5, fontname="hebo", color=MUTED)
    page.insert_text((508, top + 16), "AMOUNT", fontsize=7.5, fontname="hebo", color=MUTED)
    rows = [
        ("2 Sep", "Support payment received", f"+ {answers['monthly_income']}"),
        ("5 Sep", "Rent, 14 Example Lane", f"- {answers['monthly_expenses']}"),
        ("9 Sep", "Power and water", "- NZD 112"),
        ("14 Sep", "Groceries", "- NZD 186"),
        ("21 Sep", "Pharmacy", "- NZD 34"),
    ]
    y = top + 24
    for date, description, amount in rows:
        y += 30
        page.insert_text((56, y - 10), date, fontsize=10, color=INK)
        page.insert_text((130, y - 10), description, fontsize=10, color=INK)
        width = fitz.get_text_length(amount, fontsize=10)
        page.insert_text((556 - width, y - 10), amount, fontsize=10, color=INK)
        page.draw_line((46, y), (566, y), color=RULE, width=0.5)
    _footer(page, "SYNTHETIC — NO REAL ACCOUNT EXISTS")
    _save(document, path, "Bank statement, September 2026")


def create_scanned_witness_pdf(path: Path, answers: dict):
    source = fitz.open()
    page = source.new_page(width=612, height=792)
    page.draw_rect(fitz.Rect(36, 36, 576, 756), color=(0.63, 0.59, 0.5), width=1)
    page.insert_text((54, 76), "SYNTHETIC WITNESS NOTE", fontsize=11, color=(0.3, 0.28, 0.24))
    page.insert_text((54, 132), f"I have known {answers['applicant_name']} for five years.", fontsize=13, color=(0.14, 0.13, 0.12))
    page.draw_rect(fitz.Rect(60, 180, 350, 310), color=(0.65, 0.18, 0.12), width=2)
    page.insert_text((88, 225), "WITNESS VERIFIED", fontsize=16, color=(0.65, 0.18, 0.12))
    page.insert_text((88, 260), f"Known applicant: {answers['applicant_name']}", fontsize=11, color=(0.65, 0.18, 0.12))
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
    scanned = fitz.open()
    scanned_page = scanned.new_page(width=612, height=792)
    scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))
    _save(scanned, path, "Witness note (scanned)")
    source.close()


def generate_samples():
    vault = vault_dir()
    vault.mkdir(parents=True, exist_ok=True)
    answers = {key: answer for key, _, answer in FORM_FIELDS}
    create_form(DOCS / "renewal_form.pdf")
    create_identity_card(vault / "identity_card.pdf", answers)
    create_assessment_letter(vault / "assessment_letter.pdf", answers)
    create_bank_statement(vault / "bank_statement.pdf", answers)
    create_scanned_witness_pdf(vault / "witness_note_scan.pdf", answers)
    return [DOCS / "renewal_form.pdf", *sorted(vault.glob("*.pdf"))]


if __name__ == "__main__":
    generated = generate_samples()
    print(f"Generated {len(generated)} synthetic PDFs in {DOCS}")
