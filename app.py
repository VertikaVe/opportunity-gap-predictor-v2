"""
app.py
======
The Opportunity Gap Predictor - Streamlit MVP.
"""

import streamlit as st

from src import database
from src.eligibility import ELIGIBLE, POSSIBLY_ELIGIBLE, NOT_ELIGIBLE
from src.profile import StudentProfile, manual_profile
from src.recommendation import rank_opportunities, recommend_skills_to_learn
from src.resume_parser import parse_resume
from src.roadmap_ui import render_roadmap_page
from src.alerts import global_alerts, personal_alerts_for_session
from src import opportunity_manager
from src.application_assistant import launch_application_assistant


# --------------------------------------------------------------------------
# Page config + custom styling
# --------------------------------------------------------------------------

st.set_page_config(
    page_title="Opportunity Gap Predictor",
    page_icon="🎯",
    layout="wide",
)

CUSTOM_CSS = """
<style>
.opp-card {
    border: 1px solid rgba(120,120,120,0.25);
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 14px;
    background: rgba(120,120,120,0.04);
}
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 6px;
}
.badge-eligible { background: #1f9d55; color: white; }
.badge-possibly { background: #c98a1f; color: white; }
.badge-not { background: #b3413a; color: white; }
.badge-demo { background: #6b6b6b; color: white; }
.badge-closing { background: #b3413a; color: white; }
.badge-open { background: #2b6cb0; color: white; }
.skill-chip {
    display: inline-block;
    background: rgba(43,108,176,0.12);
    color: #2b6cb0;
    border-radius: 999px;
    padding: 2px 10px;
    margin: 2px 4px 2px 0;
    font-size: 0.8rem;
}
.skill-chip-missing {
    background: rgba(179,65,58,0.12);
    color: #b3413a;
}
.hero-title {
    font-size: 2.2rem;
    font-weight: 800;
    margin-bottom: 0.2rem;
}
.hero-subtitle {
    font-size: 1.05rem;
    color: #888;
    margin-bottom: 1.4rem;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------------

database.init_db()

if "synced" not in st.session_state:
    opportunity_manager.sync_all()
    st.session_state["synced"] = True

if "student" not in st.session_state:
    st.session_state["student"] = None


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------

def badge(text: str, css_class: str) -> str:
    return f'<span class="badge {css_class}">{text}</span>'


def eligibility_badge(status: str) -> str:
    mapping = {
        ELIGIBLE: ("Eligible", "badge-eligible"),
        POSSIBLY_ELIGIBLE: ("Possibly Eligible", "badge-possibly"),
        NOT_ELIGIBLE: ("Not Eligible", "badge-not"),
    }

    text, css_class = mapping.get(
        status,
        (status, "badge-possibly"),
    )

    return badge(text, css_class)


def status_badge(status: str) -> str:
    mapping = {
        "OPEN": ("Open", "badge-open"),
        "CLOSING_SOON": ("Closing Soon", "badge-closing"),
        "EXPIRED": ("Expired", "badge-not"),
        "CLOSED": ("Closed", "badge-not"),
    }

    text, css_class = mapping.get(
        status,
        (status, "badge-possibly"),
    )

    return badge(text, css_class)


def skill_chips(skills, missing=False) -> str:
    css_class = "skill-chip-missing" if missing else "skill-chip"

    if not skills:
        return '<span style="color:#888;">None</span>'

    return "".join(
        f'<span class="skill-chip {css_class}">{s}</span>'
        for s in skills
    )


# --------------------------------------------------------------------------
# Sidebar navigation
# --------------------------------------------------------------------------

st.sidebar.title("🎯 Opportunity Gap Predictor")

page = st.sidebar.radio(
    "Navigate",
    [
        "Landing / Upload",
        "Dashboard",
        "Opportunities",
        "Skill Gaps",
        "Roadmap",
        "Profile",
        "Alerts",
    ],
)

if st.session_state["student"]:
    st.sidebar.success(
        f"Profile loaded: {st.session_state['student'].name or 'Unnamed'}"
    )
else:
    st.sidebar.info(
        "No profile yet - start on 'Landing / Upload'."
    )


with st.sidebar.expander("Data sources"):

    for row in database.get_update_log(limit=6):
        icon = "✅" if row["status"] == "SUCCESS" else "⛔"

        st.write(
            f"{icon} **{row['source']}** - {row['status']}"
        )

    st.caption(
        "Only clearly-labeled DEMO DATA is currently live. See README.md."
    )

    if st.button("Refresh opportunities now"):

        summary = opportunity_manager.sync_all()

        st.success(
            f"Added {summary['added']}, "
            f"updated {summary['updated']}, "
            f"expired {summary['expired']}."
        )

        st.rerun()


# --------------------------------------------------------------------------
# Page: Landing / Upload
# --------------------------------------------------------------------------

if page == "Landing / Upload":

    st.markdown(
        '<div class="hero-title">'
        'Find internships you\'re actually eligible for.'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="hero-subtitle">'
        'Upload your resume to see which opportunities you match, '
        'what\'s missing, and a roadmap to close the gap.'
        '</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "🔒 **Privacy:** your resume is processed in memory for this "
        "session only. It is never saved to disk or to a database."
    )

    tab_upload, tab_manual = st.tabs(
        ["Upload Resume (PDF)", "Enter Skills Manually"]
    )

    # Resume upload
    with tab_upload:

        uploaded_file = st.file_uploader(
            "Select your resume PDF",
            type=["pdf"],
        )

        if uploaded_file is not None:

            if st.button("Analyze Resume", type="primary"):

                with st.spinner("Extracting your profile..."):
                    profile = parse_resume(uploaded_file)

                st.session_state["student"] = profile

                if profile.is_empty():

                    st.warning(
                        "We couldn't extract usable information from this PDF "
                        "(it may be a scanned/image-only resume with no text layer). "
                        "Try 'Enter Skills Manually' instead."
                    )

                else:

                    st.success(
                        f"Resume received: **{uploaded_file.name}** "
                        "- profile extracted below."
                    )

                    c1, c2, c3 = st.columns(3)

                    c1.metric("Name", profile.name or "Not found")
                    c2.metric("Degree", profile.degree or "Not found")
                    c3.metric(
                        "Graduation Year",
                        profile.graduation_year or "Not found",
                    )

                    st.write(
                        "**Skills found:**",
                        " ".join(f"`{s}`" for s in profile.skills)
                        or "None found",
                    )

                    st.caption(
                        "This is a best-effort heuristic extraction, "
                        "not guaranteed to be complete or perfectly accurate. "
                        "Please check the Profile page and correct anything wrong."
                    )

    # Manual profile
    with tab_manual:

        with st.form("manual_profile_form"):

            name = st.text_input("Name", value="")
            email = st.text_input("Email", value="")
            phone = st.text_input("Phone", value="")
            college = st.text_input("College / University", value="")
            city = st.text_input("City", value="")
            state = st.text_input("State", value="")
            country = st.text_input("Country", value="India")

            skills_raw = st.text_area(
                "Your skills (comma-separated)",
                value="",
            )

            degree = st.text_input(
                "Degree (e.g. B.Tech)",
                value="",
            )

            branch = st.text_input(
                "Branch (e.g. CSE)",
                value="",
            )

            col1, col2, col3 = st.columns(3)

            graduation_year_raw = col1.text_input(
                "Graduation year (optional)",
                value="",
            )

            semester_raw = col2.text_input(
                "Current semester (optional)",
                value="",
            )

            cgpa_raw = col3.text_input(
                "CGPA (optional)",
                value="",
            )

            submitted = st.form_submit_button(
                "Save Profile",
                type="primary",
            )

        if submitted:

            def optional_int(value):
                try:
                    return int(value) if value.strip() else None
                except ValueError:
                    return None

            def optional_float(value):
                try:
                    number = float(value) if value.strip() else None

                    return (
                        number
                        if number is not None and 0 <= number <= 10
                        else None
                    )

                except ValueError:
                    return None

            skills = [
                s.strip()
                for s in skills_raw.split(",")
                if s.strip()
            ]

            st.session_state["student"] = manual_profile(
                name=name or None,
                skills=skills,
                degree=degree or None,
                branch=branch or None,
                graduation_year=optional_int(graduation_year_raw),
                semester=optional_int(semester_raw),
                cgpa=optional_float(cgpa_raw),
                email=email or None,
                phone=phone or None,
                college=college or None,
                city=city or None,
                state=state or None,
                country=country or None,
            )

            st.success(
                "Profile saved. Head to the Dashboard to see your matches."
            )


# --------------------------------------------------------------------------
# Shared guard
# --------------------------------------------------------------------------

elif st.session_state["student"] is None:

    st.warning(
        "No profile yet. Go to **Landing / Upload** first."
    )


# --------------------------------------------------------------------------
# Main application pages
# --------------------------------------------------------------------------

else:

    student: StudentProfile = st.session_state["student"]

    all_opportunities = database.get_all_opportunities(
        include_expired=True
    )

    active_opportunities = [
        o for o in all_opportunities
        if o["status"] != "EXPIRED"
    ]


    # ----------------------------------------------------------------------
    # Page: Dashboard
    # ----------------------------------------------------------------------

    if page == "Dashboard":

        st.header("Dashboard")

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Skills on file",
            len(student.skills),
        )

        ranked_all = rank_opportunities(
            student,
            active_opportunities,
            top_n=len(active_opportunities) or 1,
        )

        eligible_now = [
            r for r in ranked_all
            if r["eligibility_status"] == ELIGIBLE
        ]

        possibly = [
            r for r in ranked_all
            if r["eligibility_status"] == POSSIBLY_ELIGIBLE
        ]

        c2.metric(
            "Opportunities you're eligible for",
            len(eligible_now),
        )

        c3.metric(
            "Possibly eligible",
            len(possibly),
        )

        closing_soon = [
            o for o in active_opportunities
            if o["status"] == "CLOSING_SOON"
        ]

        c4.metric(
            "Deadlines closing soon",
            len(closing_soon),
        )

        st.subheader("Opportunities you can apply to now")

        for r in eligible_now[:3]:

            st.markdown(
                f'<div class="opp-card">'
                f'<b>{r["role"]}</b> @ {r["company"]} &nbsp;'
                f'{eligibility_badge(r["eligibility_status"])}&nbsp;'
                f'<b>{r["match_score"]}% match</b><br>'
                f'Matched: {skill_chips(r["matched_skills"])}<br>'
                f'Missing: {skill_chips(r["missing_skills"], missing=True)}'
                f'</div>',
                unsafe_allow_html=True,
            )

        if not eligible_now:

            st.caption(
                "No current opportunities match your eligibility yet "
                "- check the Roadmap tab."
            )

        st.subheader("Your biggest opportunity gaps")

        gaps = recommend_skills_to_learn(
            student,
            active_opportunities,
            top_n=5,
        )

        if gaps:

            for g in gaps:

                st.write(
                    f"- **{g['skill']}** - missing from your profile; "
                    f"required by {g['opportunity_count']} relevant opportunities"
                )

        else:

            st.success(
                "No missing required skills found in the currently relevant opportunities."
            )

        st.subheader("Deadlines coming soon")

        for o in sorted(
            closing_soon,
            key=lambda x: x["deadline"] or "",
        )[:5]:

            st.write(
                f"- {o['role']} @ {o['company']} "
                f"- deadline **{o['deadline']}**"
            )


    # ----------------------------------------------------------------------
    # Page: Opportunities
    # ----------------------------------------------------------------------

    elif page == "Opportunities":

        st.header("Opportunities")

        f1, f2, f3 = st.columns(3)

        eligibility_filter = f1.multiselect(
            "Eligibility",
            [
                "ELIGIBLE",
                "POSSIBLY_ELIGIBLE",
                "NOT_ELIGIBLE",
            ],
            default=[
                "ELIGIBLE",
                "POSSIBLY_ELIGIBLE",
                "NOT_ELIGIBLE",
            ],
        )

        role_type_filter = f2.multiselect(
            "Role type",
            sorted({
                o["role_type"]
                for o in active_opportunities
                if o["role_type"]
            }),
            default=None,
        )

        show_expired = f3.checkbox(
            "Include expired/closed",
            value=False,
        )

        pool = (
            all_opportunities
            if show_expired
            else active_opportunities
        )

        ranked = rank_opportunities(
            student,
            pool,
            top_n=len(pool) or 1,
        )

        ranked = [
            r for r in ranked
            if r["eligibility_status"] in eligibility_filter
        ]

        if role_type_filter:

            ranked = [
                r for r in ranked
                if r["opportunity"]["role_type"] in role_type_filter
            ]

        st.caption(
            f"{len(ranked)} opportunities shown, "
            "ranked by eligibility then match score."
        )

        for r in ranked:

            opp = r["opportunity"]

            demo_tag = (
                badge("DEMO DATA", "badge-demo")
                if opp["is_demo"]
                else ""
            )

            with st.expander(
                f"{opp['role']} @ {opp['company']} "
                f"— {r['match_score']}% match"
            ):

                st.markdown(
                    f'{eligibility_badge(r["eligibility_status"])}'
                    f'{status_badge(opp["status"])}'
                    f'{demo_tag}',
                    unsafe_allow_html=True,
                )

                st.write(opp["description"])

                st.write(
                    f"**Location:** {opp['location'] or 'Not specified'} "
                    f"| **Work mode:** {opp['work_mode'] or 'Not specified'} "
                    f"| **Deadline:** {opp['deadline'] or 'Not specified'}"
                )

                st.write("**Matched skills:**")

                st.markdown(
                    skill_chips(r["matched_skills"]),
                    unsafe_allow_html=True,
                )

                st.write("**Missing required skills:**")

                st.markdown(
                    skill_chips(
                        r["missing_skills"],
                        missing=True,
                    ),
                    unsafe_allow_html=True,
                )

                st.write("**Why this result:**")

                for w in r["why"]:
                    st.write(f"- {w}")

                st.caption(
                    f"Source: {opp['source']} "
                    f"| Last checked: {opp['last_checked']}"
                )

                # Auto-Apply integration
                if opp["application_url"]:

                    st.link_button(
                        "View Official Application",
                        opp["application_url"],
                    )

                    if st.button(
                        "Auto-Fill Application",
                        key=f"autofill_{opp['id']}",
                    ):

                        try:
                            launch_application_assistant(
                                opp["application_url"],
                                student,
                            )

                            st.success(
                                "Application page opened! "
                                "Available profile details are being filled."
                            )

                            st.info(
                                "Review all details manually. "
                                "Submit the application yourself."
                            )

                        except Exception as error:
                            st.error(
                                f"Could not open application: {error}"
                            )


    # ----------------------------------------------------------------------
    # Page: Skill Gaps
    # ----------------------------------------------------------------------

    elif page == "Skill Gaps":

        st.header("Skill Gap Dashboard")

        st.caption(
            "Prioritized by how many opportunities you're "
            "eligible/possibly-eligible for require each skill."
        )

        gaps = recommend_skills_to_learn(
            student,
            active_opportunities,
            top_n=10,
        )

        if not gaps:

            st.success(
                "No significant skill gaps found among opportunities "
                "you're eligible for right now!"
            )

        for i, g in enumerate(gaps, start=1):

            st.markdown(
                f"**{i}. {g['skill'].title()}** — "
                f"required by {g['opportunity_count']} relevant opportunities"
            )


    # ----------------------------------------------------------------------
    # Page: Personalized Roadmap
    # ----------------------------------------------------------------------

    elif page == "Roadmap":

        render_roadmap_page(
            student,
            active_opportunities,
        )


    # ----------------------------------------------------------------------
    # Page: Profile
    # ----------------------------------------------------------------------

    elif page == "Profile":

        st.header("Your Profile")

        st.caption(
            "Stored only for this browser session "
            "- never saved to disk or a database."
        )

        with st.form("edit_profile"):

            name = st.text_input(
                "Name",
                value=student.name or "",
            )

            skills_raw = st.text_area(
                "Skills (comma-separated)",
                value=", ".join(student.skills),
            )

            degree = st.text_input(
                "Degree",
                value=student.degree or "",
            )

            branch = st.text_input(
                "Branch",
                value=student.branch or "",
            )

            col1, col2, col3 = st.columns(3)

            email = st.text_input(
                "Email",
                value=student.email or "",
            )

            phone = st.text_input(
                "Phone",
                value=student.phone or "",
            )

            college = st.text_input(
                "College / University",
                value=student.college or "",
            )

            graduation_year_raw = col1.text_input(
                "Graduation year (optional)",
                value=str(student.graduation_year or ""),
            )

            semester_raw = col2.text_input(
                "Semester (optional)",
                value=str(student.semester or ""),
            )

            cgpa_raw = col3.text_input(
                "CGPA (optional)",
                value=str(student.cgpa or ""),
            )

            save = st.form_submit_button(
                "Update Profile",
                type="primary",
            )

        if save:

            def optional_int(value):

                try:
                    return int(value) if value.strip() else None

                except ValueError:
                    return None

            def optional_float(value):

                try:

                    number = float(value) if value.strip() else None

                    return (
                        number
                        if number is not None and 0 <= number <= 10
                        else None
                    )

                except ValueError:
                    return None

            st.session_state["student"] = manual_profile(
                name=name or None,
                skills=[
                    s.strip()
                    for s in skills_raw.split(",")
                    if s.strip()
                ],
                degree=degree or None,
                branch=branch or None,
                graduation_year=optional_int(graduation_year_raw),
                semester=optional_int(semester_raw),
                cgpa=optional_float(cgpa_raw),
                email=email or None,
                phone=phone or None,
                college=college or None,
            )

            st.success("Profile updated.")

        if student.projects:

            st.subheader("Projects (from resume)")

            for p in student.projects:
                st.write(f"- {p}")

        if student.certifications:

            st.subheader("Certifications (from resume)")

            for c in student.certifications:
                st.write(f"- {c}")


    # ----------------------------------------------------------------------
    # Page: Alerts
    # ----------------------------------------------------------------------

    elif page == "Alerts":

        st.header("Alerts")

        st.subheader("Relevant to you right now")

        personal = personal_alerts_for_session(
            student,
            active_opportunities,
        )

        if not personal:
            st.caption("Nothing urgent right now.")

        for a in personal[:10]:
            st.write(f"🔔 {a['message']}")

        st.subheader(
            "Global feed (new opportunities & deadlines)"
        )

        feed = global_alerts(limit=20)

        if not feed:

            st.caption(
                "No alerts yet - try 'Refresh opportunities now' in the sidebar."
            )

        for a in feed:

            ts = a["created_at"][:16].replace("T", " ")

            st.write(
                f"[{ts}] {a['message']}"
            )