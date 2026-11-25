from datetime import date, timedelta

from src.profile import StudentProfile
from src import roadmap as rm


def _opportunity(**overrides):
    base = {
        "id": "o1", "company": "Acme", "role": "Intern",
        "required_skills": ["Excel"], "preferred_skills": [],
        "degree_allowed": None, "branch_allowed": None,
        "graduation_year_min": None, "graduation_year_max": None,
        "semester_min": None, "semester_max": None, "cgpa_min": None,
        "experience_required": None, "deadline": None, "status": "OPEN",
    }
    base.update(overrides)
    return base


def test_get_topics_for_goal_is_cumulative_and_curated_for_known_skill():
    foundations, curated = rm.get_topics_for_goal("Excel", "foundations")
    project, _ = rm.get_topics_for_goal("Excel", "project")
    assert curated is True
    assert len(project) > len(foundations)
    foundation_topics = {t["topic"] for t in foundations}
    project_topics = {t["topic"] for t in project}
    assert foundation_topics.issubset(project_topics)


def test_get_topics_for_goal_falls_back_to_generic_for_unknown_skill():
    topics, curated = rm.get_topics_for_goal("some-made-up-skill-xyz", "foundations")
    assert curated is False
    assert len(topics) > 0


def test_build_daily_schedule_does_not_split_a_topic_and_respects_budget():
    topics = [
        {"topic": "A", "hours": 2, "task": "do A"},
        {"topic": "B", "hours": 2, "task": "do B"},
        {"topic": "C", "hours": 1, "task": "do C"},
    ]
    schedule = rm.build_daily_schedule(topics, hours_per_day=3)
    assert schedule[0]["hours"] <= 3
    total_topics_scheduled = sum(len(day["topics"]) for day in schedule)
    assert total_topics_scheduled == 3


def test_build_daily_schedule_gives_oversized_topic_its_own_day():
    topics = [{"topic": "Huge", "hours": 10, "task": "a lot"}]
    schedule = rm.build_daily_schedule(topics, hours_per_day=2)
    assert len(schedule) == 1
    assert schedule[0]["hours"] == 10


def test_assess_deadline_feasibility_no_deadline():
    result = rm.assess_deadline_feasibility(5, None)
    assert result["status"] == "no_deadline"


def test_assess_deadline_feasibility_achievable():
    far_deadline = (date.today() + timedelta(days=30)).isoformat()
    result = rm.assess_deadline_feasibility(5, far_deadline)
    assert result["status"] == "achievable"


def test_assess_deadline_feasibility_not_achievable():
    near_deadline = (date.today() + timedelta(days=2)).isoformat()
    result = rm.assess_deadline_feasibility(10, near_deadline)
    assert result["status"] == "not_achievable"
    assert "may not be realistically achievable" in result["message"]


def test_get_relevant_opportunities_matches_required_and_preferred():
    opportunities = [
        _opportunity(id="o1", required_skills=["Excel"]),
        _opportunity(id="o2", required_skills=["SQL"], preferred_skills=["Excel"]),
        _opportunity(id="o3", required_skills=["Java"]),
    ]
    relevant = rm.get_relevant_opportunities("Excel", opportunities)
    ids = {o["id"] for o in relevant}
    assert ids == {"o1", "o2"}


def test_build_roadmap_integration_with_real_opportunity():
    student = StudentProfile(name="Test", skills=["Python"])
    opportunities = [_opportunity(id="o1", company="Acme", role="Analyst", required_skills=["Excel", "SQL"])]
    roadmap = rm.build_roadmap("excel", "foundations", 2, student, opportunities)
    assert roadmap["skill"] == "excel"
    assert roadmap["total_hours"] > 0
    assert roadmap["days_required"] > 0
    assert len(roadmap["relevant_opportunities"]) == 1
    assert roadmap["deadline_feasibility"]["status"] == "no_deadline"


def test_build_roadmap_respects_prerequisite_note():
    student = StudentProfile(name="Test", skills=["Python"])  # no javascript
    roadmap = rm.build_roadmap("react", "foundations", 2, student, [])
    assert roadmap["prereq_note"] is not None
    assert "Javascript" in roadmap["prereq_note"]


def test_build_roadmap_no_prerequisite_note_when_student_already_has_it():
    student = StudentProfile(name="Test", skills=["JavaScript"])
    roadmap = rm.build_roadmap("react", "foundations", 2, student, [])
    assert roadmap["prereq_note"] is None


def test_compute_opportunity_impact_never_changes_eligibility():
    student = StudentProfile(name="Test", skills=["Python"], semester=1)
    opportunities = [_opportunity(id="o1", required_skills=["Excel"], semester_min=6)]
    impact = rm.compute_opportunity_impact(student, opportunities, "excel")
    assert impact["pairs"][0]["eligibility_status"] == "NOT_ELIGIBLE"


def test_compute_opportunity_impact_shows_real_score_increase():
    student = StudentProfile(name="Test", skills=["SQL"])
    opportunities = [_opportunity(id="o1", required_skills=["Excel", "SQL"])]
    impact = rm.compute_opportunity_impact(student, opportunities, "excel")
    pair = impact["pairs"][0]
    assert pair["after_score"] > pair["before_score"]
    assert "excel" not in pair["after_missing"]


def test_progress_status_transitions():
    assert rm.progress_status(0, 5) == "NOT_STARTED"
    assert rm.progress_status(3, 5) == "IN_PROGRESS"
    assert rm.progress_status(5, 5) == "COMPLETED"
    assert rm.progress_status(0, 0) == "NOT_STARTED"


def test_progress_summary_computes_remaining_hours():
    schedule = [{"day": 1, "hours": 2}, {"day": 2, "hours": 3}]
    summary = rm.progress_summary(schedule, {1})
    assert summary["completed"] == 1
    assert summary["total"] == 2
    assert summary["remaining_hours"] == 3
    assert summary["status"] == "IN_PROGRESS"


def test_get_skill_options_reuses_existing_recommendation_logic():
    student = StudentProfile(name="Test", skills=["Python"])
    opportunities = [_opportunity(id="o1", required_skills=["Excel", "Python"])]
    options = rm.get_skill_options(student, opportunities)
    assert options == [{"skill": "excel", "opportunity_count": 1}]
