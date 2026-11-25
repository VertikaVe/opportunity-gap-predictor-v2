from src.profile import manual_profile


def test_manual_profile_keeps_unknown_academic_fields_empty():
    profile = manual_profile(name=None, skills=[])
    assert profile.graduation_year is None
    assert profile.semester is None
    assert profile.cgpa is None


def test_manual_profile_accepts_contact_and_college_details():
    profile = manual_profile(
        name="Student",
        skills=["python"],
        email="student@example.com",
        phone="9876543210",
        college="Example University",
    )
    assert profile.email == "student@example.com"
    assert profile.phone == "9876543210"
    assert profile.college == "Example University"
