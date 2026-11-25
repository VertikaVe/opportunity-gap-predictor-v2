"""
roadmap_ui.py
==============
Streamlit rendering for the Roadmap page. All actual logic lives in
src/roadmap.py (pure, unit-tested); this file only turns that data into
widgets, so it's easy to re-check behavior against tests/test_roadmap.py
if the UI ever looks wrong.

How to merge this into another copy of the project
-------------------------------------------------------
1. Copy `src/roadmap.py` (replaces the old one) and this file into the
   target project's `src/` folder.
2. In that project's Roadmap page branch in `app.py`, replace the old
   roadmap code with:

       from src.roadmap_ui import render_roadmap_page
       ...
       elif page == "Roadmap":
           render_roadmap_page(student, active_opportunities)

3. This module expects `student` to expose `.skills`, `.name`, `.degree`,
   `.branch`, `.graduation_year`, `.semester`, `.cgpa` (as this project's
   StudentProfile does) and `opportunities` to be a list of dicts shaped
   like `database.get_all_opportunities()` returns here (id, company,
   role, required_skills, preferred_skills, status, deadline, ...). If
   the target project's equivalents are named differently, the only file
   that needs adapting is src/roadmap.py's calls into
   src.recommendation / src.eligibility / src.skill_processing - the UI
   layer here does not need to change.

Session state
--------------
Everything here is scoped under keys prefixed `roadmap_` so it can't
collide with other pages' session state. Per the project's own privacy
rule, this still never touches the database - roadmap progress lives
only in this browser session, same as the student profile itself.
"""

import streamlit as st

from src.roadmap import (
    GOAL_LABELS,
    GOAL_ORDER,
    build_roadmap,
    compute_opportunity_impact,
    get_skill_options,
    progress_summary,
)

HOURS_OPTIONS = [1, 1.5, 2, 3, 4]


def _hours_label(h: float) -> str:
    return f"{h:g} hour/day" if h == 1 else f"{h:g} hours/day"


def render_roadmap_page(student, opportunities) -> None:
    st.header("🎯 Personalized Skill Roadmap")
    st.caption(
        "A planning tool, not a guarantee - estimated effort, not a promise of mastery, "
        "an interview, or eligibility."
    )

    skill_options = get_skill_options(student, opportunities, top_n=10)
    if not skill_options:
        st.success(
            "No significant skill gaps found among opportunities you're eligible for right now! "
            "Check back as new opportunities are added."
        )
        return

    # ------------------------------------------------------------------
    # 1 & 3. Skill selection + goal + study time
    # ------------------------------------------------------------------
    skill_labels = [f"{o['skill'].title()}" for o in skill_options]
    selected_idx = st.selectbox(
        "Choose a skill to work on",
        options=list(range(len(skill_options))),
        format_func=lambda i: skill_labels[i],
    )
    selected = skill_options[selected_idx]
    selected_skill = selected["skill"]

    st.markdown(
        f"**Why this skill?** Required by **{selected['opportunity_count']}** relevant opportunities "
        f"you're currently eligible or possibly eligible for. Currently missing from your profile. "
        f"Learning this may improve your match with these opportunities."
    )

    col1, col2 = st.columns(2)
    with col1:
        goal = st.selectbox(
            "What is your goal?",
            options=GOAL_ORDER,
            index=2,  # default: Project Ready
            format_func=lambda g: GOAL_LABELS[g],
        )
    with col2:
        hours_per_day = st.selectbox(
            "How much time can you study per day?",
            options=HOURS_OPTIONS,
            index=2,  # default: 2 hours/day
            format_func=_hours_label,
        )

    generate = st.button("Generate Personalized Roadmap", type="primary")

    # ------------------------------------------------------------------
    # Build (or reuse) the active roadmap for this skill
    # ------------------------------------------------------------------
    if generate:
        roadmap = build_roadmap(selected_skill, goal, hours_per_day, student, opportunities)
        st.session_state["roadmap_active"] = roadmap

        progress_store = st.session_state.setdefault("roadmap_progress", {})
        last_days_store = st.session_state.setdefault("roadmap_last_days", {})
        if last_days_store.get(selected_skill) != roadmap["days_required"]:
            # Schedule shape changed (different goal/pace) - day numbers no
            # longer mean the same thing, so progress for this skill resets.
            progress_store[selected_skill] = set()
            if selected_skill in last_days_store:
                st.info("Roadmap updated for this skill - progress has been reset to match the new schedule.")
        last_days_store[selected_skill] = roadmap["days_required"]

    active = st.session_state.get("roadmap_active")
    if not active:
        st.caption("Pick a skill, goal, and study time above, then generate your roadmap.")
        return

    # ------------------------------------------------------------------
    # Summary header
    # ------------------------------------------------------------------
    st.divider()
    st.subheader(f"{active['skill'].title()} — {active['goal_label']}")
    if not active["is_curated"]:
        st.caption(
            "ℹ️ No hand-curated curriculum exists yet for this specific skill - showing a generic "
            "learning structure instead. Topics are broader than a tailored curriculum would be."
        )

    m1, m2, m3 = st.columns(3)
    m1.metric("Estimated effort", f"{active['total_hours']} hours")
    m2.metric("Your study time", _hours_label(active["hours_per_day"]))
    m3.metric("Estimated timeline", f"{active['days_required']} study days")

    if active["prereq_note"]:
        st.warning(active["prereq_note"])

    # ------------------------------------------------------------------
    # 6. Opportunity connection (shown immediately, before completion)
    # ------------------------------------------------------------------
    st.markdown("#### Why you're learning this")
    relevant = active["relevant_opportunities"]
    if relevant:
        st.write(
            f"**{active['skill'].title()}** is currently required or preferred by "
            f"**{len(relevant)}** opportunity(ies) already in the app:"
        )
        for opp in relevant:
            st.write(f"- {opp['role']} @ {opp['company']}")
    else:
        st.caption(
            "This skill isn't directly required by a currently-listed opportunity, but it's "
            "a prioritized gap based on your overall profile."
        )

    # ------------------------------------------------------------------
    # 7. Deadline-aware feasibility check
    # ------------------------------------------------------------------
    st.markdown("#### Deadline Check")
    feas = active["deadline_feasibility"]
    if feas["status"] == "no_deadline":
        st.info(feas["message"])
    elif feas["status"] == "achievable":
        st.success(f"🟢 {feas['message']}")
    else:
        st.warning(feas["message"])

    # ------------------------------------------------------------------
    # 4 & 5. Day-by-day plan
    # ------------------------------------------------------------------
    st.markdown("#### Your Daily Plan")
    progress_store = st.session_state.setdefault("roadmap_progress", {})
    completed_days = progress_store.setdefault(active["skill"], set())

    for day in active["daily_schedule"]:
        key = f"roadmap_day_{active['skill']}_{active['goal']}_{active['hours_per_day']}_{day['day']}"
        label = f"Day {day['day']} — {', '.join(day['topics'])} — {day['hours']}h"
        checked = st.checkbox(label, value=day["day"] in completed_days, key=key)
        if checked:
            completed_days.add(day["day"])
        else:
            completed_days.discard(day["day"])

        with st.expander(f"Details for Day {day['day']}", expanded=False):
            for task in day["tasks"]:
                st.write(f"📝 Task: {task}")
            for practice in day["practice"]:
                st.write(f"🔁 Practice/revision: {practice}")

    # ------------------------------------------------------------------
    # 8. Progress tracking
    # ------------------------------------------------------------------
    st.markdown("#### Progress")
    progress = progress_summary(active["daily_schedule"], completed_days)
    total = progress["total"] or 1
    st.progress(progress["completed"] / total)
    st.write(f"**Progress: {progress['completed']} / {progress['total']} days completed**")
    st.write(f"**Status:** {progress['status'].replace('_', ' ').title()}")
    st.write(f"**Estimated remaining study time:** {progress['remaining_hours']} hours")

    # ------------------------------------------------------------------
    # 9 & 10. Opportunity impact + completion state
    # ------------------------------------------------------------------
    if progress["status"] == "COMPLETED":
        st.success("🎉 Skill roadmap completed!")

        st.markdown("##### What you worked through")
        all_topics = [t for day in active["daily_schedule"] for t in day["topics"]]
        st.write(", ".join(all_topics))

        impact = compute_opportunity_impact(student, opportunities, active["skill"])
        st.markdown("##### Opportunity Impact")
        st.caption(impact["note"])

        if impact["pairs"]:
            for pair in impact["pairs"]:
                delta = round(pair["after_score"] - pair["before_score"], 2)
                st.write(
                    f"- **{pair['role']} @ {pair['company']}**: "
                    f"{pair['before_score']}% → {pair['after_score']}% "
                    f"({'+' if delta >= 0 else ''}{delta} pts) "
                    f"| Eligibility: {pair['eligibility_status'].replace('_', ' ').title()}"
                )
            st.write(
                f"Opportunities with ALL required skills covered: "
                f"{impact['before_full_coverage_count']} → {impact['after_full_coverage_count']}"
            )
        else:
            st.caption("No currently-listed opportunities require or prefer this specific skill.")

    elif progress["status"] == "IN_PROGRESS":
        st.info(f"Roadmap status: **In Progress** - {progress['completed']}/{progress['total']} days done. Complete all days to see your updated opportunity match.")
    else:
        st.caption("Roadmap status: **Not Started**. Check off a day above once you complete it.")

    # ------------------------------------------------------------------
    # 11. Next recommended skills
    # ------------------------------------------------------------------
    if active["next_skills"]:
        st.markdown("#### Recommended Next Skills")
        for i, s in enumerate(active["next_skills"], start=1):
            st.write(f"{i}. **{s['skill'].title()}** — required by {s['opportunity_count']} relevant opportunities")
