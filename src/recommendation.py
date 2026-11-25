"""
recommendation.py
==================
Combines skill-gap analysis, TF-IDF similarity, and eligibility into one
transparent match score and a human-readable "why" explanation, plus
ranking/skill-demand utilities.

Location matching is kept separate from the skill match score.
Eligibility remains a separate category and is not mixed into the score.
"""

from typing import Dict, List

import pandas as pd

from src import config
from src.eligibility import evaluate_eligibility, ELIGIBLE
from src.skill_gap import get_skill_gap_report
from src.similarity import get_tfidf_similarity


# Indian states sharing a boundary with Bihar
NEARBY_STATES = {
    "bihar": {
        "jharkhand",
        "uttar pradesh",
        "west bengal",
    }
}


def _normalize_location(value):
    """Normalize a location string for comparison."""

    if not value:
        return ""

    return " ".join(str(value).strip().lower().split())


def get_location_match(student, opportunity):
    """
    Classify location compatibility without changing skill match score.

    Priority:
    0 = Same city
    1 = Same state
    2 = Nearby state
    3 = Remote
    4 = Other location
    5 = Location unknown
    """

    student_city = _normalize_location(
        getattr(student, "city", None)
    )

    student_state = _normalize_location(
        getattr(student, "state", None)
    )

    opportunity_location = _normalize_location(
        opportunity.get("location")
    )

    work_mode = _normalize_location(
        opportunity.get("work_mode")
    )

    # Remote opportunities can be accessed from different locations.
    if (
        "remote" in work_mode
        or "remote" in opportunity_location
        or "work from home" in opportunity_location
    ):
        return {
            "location_match": "REMOTE",
            "location_priority": 3,
            "location_reason": "Remote opportunity",
        }

    # Location is not available.
    if not opportunity_location:
        return {
            "location_match": "UNKNOWN",
            "location_priority": 5,
            "location_reason": "Opportunity location not specified",
        }

    # Expected format: City, State, Country
    parts = [
        part.strip()
        for part in opportunity_location.split(",")
        if part.strip()
    ]

    opp_city = (
        _normalize_location(parts[0])
        if parts else ""
    )

    opp_state = (
        _normalize_location(parts[1])
        if len(parts) > 1 else ""
    )

    # Same city
    if (
        student_city
        and opp_city
        and student_city == opp_city
    ):
        return {
            "location_match": "SAME_CITY",
            "location_priority": 0,
            "location_reason": "Same city as your profile",
        }

    # Same state
    if (
        student_state
        and opp_state
        and student_state == opp_state
    ):
        return {
            "location_match": "SAME_STATE",
            "location_priority": 1,
            "location_reason": "Same state as your profile",
        }

    # Nearby state
    if (
        student_state
        and opp_state
        and opp_state in NEARBY_STATES.get(student_state, set())
    ):
        return {
            "location_match": "NEARBY_STATE",
            "location_priority": 2,
            "location_reason": "Opportunity is in a nearby state",
        }

    # Other locations
    return {
        "location_match": "OTHER_LOCATION",
        "location_priority": 4,
        "location_reason": "Different or unmatched location",
    }


def compute_match(student, opportunity: Dict) -> Dict:
    """
    Full match breakdown for one student/opportunity pair.

    Includes:
    - Skill-gap report
    - TF-IDF score
    - Blended skill-match score
    - Eligibility result
    - Location compatibility
    - Human-readable explanation
    """

    student_skills = getattr(student, "skills", [])

    required = opportunity.get("required_skills", [])
    preferred = opportunity.get("preferred_skills", [])

    gap = get_skill_gap_report(
        student_skills,
        required,
        preferred,
    )

    tfidf_score = (
        get_tfidf_similarity(student_skills, required) * 100
    )

    preferred_score = (
        gap["preferred_match_percentage"] or 0.0
    )

    # Original skill matching formula remains unchanged.
    match_score = (
        config.EXACT_WEIGHT * gap["match_percentage"]
        + config.PREFERRED_WEIGHT * preferred_score
        + config.TFIDF_WEIGHT * tfidf_score
    )

    eligibility = evaluate_eligibility(
        student,
        opportunity,
    )

    location_info = get_location_match(
        student,
        opportunity,
    )

    why = []

    n_required = len(set(required)) or 1

    why.append(
        f"{len(gap['matched_skills'])}/"
        f"{len(set(gap['matched_skills']) | set(gap['missing_skills'])) or n_required}"
        " required skills matched"
    )

    if gap["missing_skills"]:
        why.append(
            f"Missing required: {', '.join(gap['missing_skills'])}"
        )

    if gap["matched_preferred_skills"]:
        why.append(
            f"Also has {len(gap['matched_preferred_skills'])} "
            f"preferred skill(s): "
            f"{', '.join(gap['matched_preferred_skills'])}"
        )

    why.extend(eligibility.reasons)
    why.extend(eligibility.notes)

    # Include location explanation.
    why.append(location_info["location_reason"])

    return {
        "opportunity_id": opportunity["id"],
        "company": opportunity["company"],
        "role": opportunity["role"],

        "match_score": round(match_score, 2),

        "matched_skills": gap["matched_skills"],
        "missing_skills": gap["missing_skills"],

        "matched_preferred_skills": gap["matched_preferred_skills"],
        "missing_preferred_skills": gap["missing_preferred_skills"],

        "tfidf_score": round(tfidf_score, 2),

        "eligibility_status": eligibility.status,
        "eligibility_reasons": eligibility.reasons,
        "eligibility_notes": eligibility.notes,

        "location_match": location_info["location_match"],
        "location_priority": location_info["location_priority"],
        "location_reason": location_info["location_reason"],

        "why": why,

        "opportunity": opportunity,
    }


def rank_opportunities(
    student,
    opportunities: List[Dict],
    top_n: int = config.DEFAULT_TOP_N,
) -> List[Dict]:
    """
    Rank opportunities using:

    1. Eligibility category
    2. Skill match score
    3. Location priority as a tie-breaker

    Location does not increase or decrease the skill match score.
    """

    results = [
        compute_match(student, opp)
        for opp in opportunities
    ]

    tier = {
        ELIGIBLE: 0,
        "POSSIBLY_ELIGIBLE": 1,
        "NOT_ELIGIBLE": 2,
    }

    results.sort(
        key=lambda r: (
            tier.get(r["eligibility_status"], 3),
            -r["match_score"],
            r["location_priority"],
        )
    )

    return results[:top_n]


def recommend_skills_to_learn(
    student,
    opportunities: List[Dict],
    top_n: int = config.DEFAULT_TOP_N,
) -> List[Dict]:
    """
    Rank missing skills by how many opportunities the student is
    ELIGIBLE or POSSIBLY_ELIGIBLE for.
    """

    from src.skill_gap import get_missing_skills

    skill_frequency: Dict[str, int] = {}

    for opp in opportunities:

        eligibility = evaluate_eligibility(
            student,
            opp,
        )

        if eligibility.status == "NOT_ELIGIBLE":
            continue

        for skill in get_missing_skills(
            getattr(student, "skills", []),
            opp.get("required_skills", []),
        ):
            skill_frequency[skill] = (
                skill_frequency.get(skill, 0) + 1
            )

    ranked = sorted(
        skill_frequency.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    return [
        {
            "skill": skill,
            "opportunity_count": count,
        }
        for skill, count in ranked[:top_n]
    ]


def top_demanded_skills(
    opportunities: List[Dict],
    top_n: int = config.DEFAULT_TOP_N,
) -> List[Dict]:

    from src.skill_processing import normalize_skill_list

    skill_frequency: Dict[str, int] = {}

    for opp in opportunities:

        for skill in normalize_skill_list(
            opp.get("required_skills", [])
        ):
            skill_frequency[skill] = (
                skill_frequency.get(skill, 0) + 1
            )

    ranked = sorted(
        skill_frequency.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    return [
        {
            "skill": skill,
            "opportunity_count": count,
        }
        for skill, count in ranked[:top_n]
    ]