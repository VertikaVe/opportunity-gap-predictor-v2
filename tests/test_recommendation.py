from src.profile import StudentProfile
from src.recommendation import (
    recommend_skills_to_learn,
    get_location_match,
)


def test_recommendations_do_not_show_skills_already_in_student_profile():
    student = StudentProfile(
        name="Test Student",
        skills=["Python", "SQL"],
    )
    opportunities = [
        {
            "id": "1",
            "company": "Example Co",
            "role": "Software Intern",
            "required_skills": ["python", "typescript", "sql"],
            "preferred_skills": [],
            "degree_allowed": None,
            "branch_allowed": None,
            "graduation_year_min": None,
            "graduation_year_max": None,
            "semester_min": None,
            "semester_max": None,
            "cgpa_min": None,
            "deadline": None,
        }
    ]

    result = recommend_skills_to_learn(student, opportunities, top_n=10)

    assert result == [{"skill": "typescript", "opportunity_count": 1}]
    assert "python" not in [item["skill"] for item in result]
def test_same_city_location_match():
    student = StudentProfile(
        name="Test Student",
        city="Patna",
        state="Bihar",
    )

    opportunity = {
        "location": "Patna, Bihar, India",
        "work_mode": "On-site",
    }

    result = get_location_match(student, opportunity)

    assert result["location_match"] == "SAME_CITY"
    assert result["location_priority"] == 0


def test_same_state_location_match():
    student = StudentProfile(
        name="Test Student",
        city="Patna",
        state="Bihar",
    )

    opportunity = {
        "location": "Gaya, Bihar, India",
        "work_mode": "On-site",
    }

    result = get_location_match(student, opportunity)

    assert result["location_match"] == "SAME_STATE"
    assert result["location_priority"] == 1


def test_remote_location_match():
    student = StudentProfile(
        name="Test Student",
        city="Patna",
        state="Bihar",
    )

    opportunity = {
        "location": "Bangalore, Karnataka, India",
        "work_mode": "Remote",
    }

    result = get_location_match(student, opportunity)

    assert result["location_match"] == "REMOTE"
    assert result["location_priority"] == 3

def test_unknown_location_match():
    student = StudentProfile(
        name="Test Student",
        city="Patna",
        state="Bihar",
    )

    opportunity = {
        "location": None,
        "work_mode": None,
    }

    result = get_location_match(student, opportunity)

    assert result["location_match"] == "UNKNOWN"
    assert result["location_priority"] == 5