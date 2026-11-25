from pathlib import Path

from src.resume_parser import parse_resume

FIXTURE = Path(__file__).parent / "fixtures" / "sample_resume.pdf"


def test_parse_resume_extracts_email_and_name():
    profile = parse_resume(str(FIXTURE))
    assert profile.email == "ananya.rao@example.com"
    assert profile.name == "Ananya Rao"


def test_parse_resume_extracts_skills():
    profile = parse_resume(str(FIXTURE))
    assert "python" in profile.skills
    assert "sql" in profile.skills


def test_parse_resume_extracts_graduation_year_and_semester():
    profile = parse_resume(str(FIXTURE))
    assert profile.graduation_year == 2027
    assert profile.semester == 5


def test_parse_resume_extracts_cgpa():
    profile = parse_resume(str(FIXTURE))
    assert profile.cgpa == 8.1

def test_parse_resume_handles_empty_pdf_gracefully(tmp_path):
    from pypdf import PdfWriter

    blank_pdf = tmp_path / "blank.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)

    with blank_pdf.open("wb") as pdf_file:
        writer.write(pdf_file)

    profile = parse_resume(str(blank_pdf))

    assert profile.is_empty()


def test_parse_resume_does_not_guess_semester_from_year_of_study():
    from src.resume_parser import _extract_semester

    assert _extract_semester("Currently studying in 3rd year") is None


def test_parse_resume_handles_invalid_pdf_gracefully():
    from io import BytesIO

    profile = parse_resume(BytesIO(b"this is not a PDF"))
    assert profile.is_empty()
