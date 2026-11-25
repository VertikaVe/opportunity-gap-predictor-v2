"""
roadmap.py
==========
Generates a realistic, personalized, deadline-aware learning roadmap for
ONE skill at a time, built entirely from the project's existing
skill-gap/matching/eligibility logic - no parallel ranking system, no
invented opportunities.

This module is pure logic (no Streamlit import), so it can be unit
tested directly - see tests/test_roadmap.py - and reused by any UI layer
(src/roadmap_ui.py renders it for this project's Streamlit app).

What changed from the previous version
------------------------------------------
The old `build_roadmap()` dumped every missing skill into one flat,
week-numbered list with no real curriculum, no time-of-day budgeting, and
no connection back to which opportunities it would actually help with.
This version instead:
  - works on ONE skill at a time (chosen from the existing
    `recommendation.recommend_skills_to_learn()` ranking - the same
    opportunity-gap prioritization already used elsewhere in the app),
  - uses a real, hand-written curriculum (`SKILL_ROADMAPS`) for common
    skills, broken into stages per learning goal (Foundations / Interview
    Ready / Project Ready / Opportunity Ready), each topic carrying its
    own realistic effort estimate in hours,
  - falls back to a clearly-labeled GENERIC structure (not a fabricated
    curriculum) for a skill with no hand-written entry yet,
  - turns total effort hours + the student's chosen daily study time into
    a real day-by-day schedule (no day is a placeholder - each has a
    topic, an hour budget, and a task),
  - checks the nearest REAL deadline (from the existing opportunity data
    only) among opportunities that actually require the skill and that
    the student isn't flatly NOT_ELIGIBLE for, and reports whether the
    roadmap is realistically achievable in time - never a fabricated
    deadline,
  - reports opportunity impact by re-running the existing `compute_match`
    logic with the skill hypothetically added to the student's profile,
    and is explicit that eligibility (degree/branch/year/semester/CGPA)
    is a SEPARATE concern that learning a skill never changes on its own.

Public functions (used by src/roadmap_ui.py)
------------------------------------------------
- get_skill_options(student, opportunities)
- get_relevant_opportunities(skill, opportunities)
- get_nearest_deadline(skill, student, opportunities)
- build_roadmap(skill, goal, hours_per_day, student, opportunities)
- compute_opportunity_impact(student, opportunities, skill)
- progress_summary(daily_schedule, completed_days)
"""

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Set

from src.recommendation import compute_match, recommend_skills_to_learn
from src.skill_processing import normalize_skill, normalize_skill_list

GOAL_ORDER = ["foundations", "interview", "project", "opportunity_ready"]
GOAL_LABELS = {
    "foundations": "Foundations",
    "interview": "Interview Ready",
    "project": "Project Ready",
    "opportunity_ready": "Opportunity Ready",
}

# --------------------------------------------------------------------------
# Hand-written curricula for common skills.
# --------------------------------------------------------------------------
# Each skill maps goal-level keys to the TOPICS ADDED AT THAT LEVEL ONLY.
# get_topics_for_goal() below concatenates foundations -> interview ->
# project -> opportunity_ready cumulatively, so "Project Ready" includes
# everything in "Foundations" and "Interview Ready" plus its own topics.
# Every topic has an honest, realistic hour estimate for a college
# student learning outside of class - these are estimates, not guarantees.
SKILL_ROADMAPS: Dict[str, Dict[str, List[Dict]]] = {
    "python": {
        "foundations": [
            {"topic": "Syntax, variables, and data types", "hours": 3, "task": "Write 10 small scripts covering strings, numbers, and lists."},
            {"topic": "Control flow (if/for/while)", "hours": 3, "task": "Solve 5 basic logic problems using loops and conditionals."},
            {"topic": "Functions and modules", "hours": 3, "task": "Refactor your earlier scripts into reusable functions."},
        ],
        "interview": [
            {"topic": "Data structures: lists, dicts, sets, tuples", "hours": 4, "task": "Practice 8 problems manipulating each structure.", "practice": "Review time-complexity of common operations."},
            {"topic": "Common interview patterns (two pointers, hashing)", "hours": 5, "task": "Solve 6 easy/medium problems using these patterns."},
        ],
        "project": [
            {"topic": "File I/O and working with APIs/requests", "hours": 4, "task": "Build a script that fetches and processes data from a public API."},
            {"topic": "Mini project: a small CLI or data tool", "hours": 8, "task": "Build and document one complete small project end-to-end."},
        ],
        "opportunity_ready": [
            {"topic": "Code quality: testing basics and clean structure", "hours": 3, "task": "Add simple tests to your mini project."},
            {"topic": "Mock interview / resume talking points for this project", "hours": 2, "task": "Practice explaining your project out loud in under 2 minutes."},
        ],
    },
    "sql": {
        "foundations": [
            {"topic": "SELECT, WHERE, ORDER BY basics", "hours": 3, "task": "Write 10 queries against a sample database (e.g. SQLite's chinook.db)."},
            {"topic": "Aggregations: GROUP BY, COUNT, SUM, AVG", "hours": 3, "task": "Write 6 reporting-style queries."},
        ],
        "interview": [
            {"topic": "JOINs (inner, left, self-join)", "hours": 4, "task": "Solve 8 JOIN-based problems.", "practice": "Draw out the tables before writing each JOIN."},
            {"topic": "Subqueries and common table expressions (CTEs)", "hours": 3, "task": "Rewrite 3 nested-subquery solutions using CTEs."},
        ],
        "project": [
            {"topic": "Window functions", "hours": 4, "task": "Use RANK/ROW_NUMBER to solve 4 ranking problems."},
            {"topic": "Mini project: a small reporting dashboard query set", "hours": 6, "task": "Write a set of queries that answer 5 real business questions on a sample dataset."},
        ],
        "opportunity_ready": [
            {"topic": "Query performance basics (indexes, EXPLAIN)", "hours": 3, "task": "Run EXPLAIN on 3 of your slower queries and note what you'd optimize."},
            {"topic": "Mock interview: SQL whiteboard practice", "hours": 2, "task": "Solve 2 timed SQL problems without an IDE's autocomplete."},
        ],
    },
    "excel": {
        "foundations": [
            {"topic": "Core formulas (SUM, IF, VLOOKUP/XLOOKUP)", "hours": 3, "task": "Build a small expense tracker using these formulas."},
            {"topic": "Sorting, filtering, and basic formatting", "hours": 2, "task": "Clean and organize a messy sample dataset."},
        ],
        "interview": [
            {"topic": "Pivot tables", "hours": 3, "task": "Summarize a sample sales dataset with 3 different pivot views."},
            {"topic": "Common interview questions on formulas & logic", "hours": 2, "task": "Practice explaining VLOOKUP vs INDEX/MATCH out loud."},
        ],
        "project": [
            {"topic": "Charts and dashboards", "hours": 3, "task": "Build a one-page dashboard summarizing a sample dataset."},
            {"topic": "Mini project: monthly report template", "hours": 4, "task": "Build a reusable report template with formulas + a chart."},
        ],
        "opportunity_ready": [
            {"topic": "Data cleaning at scale (Power Query basics)", "hours": 3, "task": "Import and clean a larger, messier dataset with Power Query."},
            {"topic": "Presenting your dashboard", "hours": 1, "task": "Practice walking through your dashboard in under 2 minutes."},
        ],
    },
    "power bi": {
        "foundations": [
            {"topic": "Connecting data sources and the Power BI interface", "hours": 2, "task": "Import a sample CSV and explore the data model view."},
            {"topic": "Basic visuals (bar, line, card)", "hours": 3, "task": "Build 4 basic visuals from a sample dataset."},
        ],
        "interview": [
            {"topic": "DAX basics (calculated columns & measures)", "hours": 4, "task": "Write 5 DAX measures (e.g. running total, % of total)."},
        ],
        "project": [
            {"topic": "Relationships between tables", "hours": 3, "task": "Model a small multi-table dataset and build a relationship diagram."},
            {"topic": "Mini project: a sales/operations dashboard", "hours": 6, "task": "Build a 3-page interactive dashboard with filters."},
        ],
        "opportunity_ready": [
            {"topic": "Publishing and sharing reports", "hours": 2, "task": "Publish your dashboard and write a one-paragraph summary of its insights."},
        ],
    },
    "javascript": {
        "foundations": [
            {"topic": "Syntax, variables, functions", "hours": 3, "task": "Write 8 small scripts covering functions and array methods."},
            {"topic": "DOM basics", "hours": 3, "task": "Build a page that updates content on a button click."},
        ],
        "interview": [
            {"topic": "Array/object methods (map, filter, reduce)", "hours": 4, "task": "Solve 8 problems using these methods instead of loops."},
            {"topic": "Async JS (promises, async/await)", "hours": 4, "task": "Write a script that fetches data from a public API asynchronously."},
        ],
        "project": [
            {"topic": "Working with a small framework or vanilla fetch-based app", "hours": 5, "task": "Build a small interactive app (e.g. a to-do list) end-to-end."},
            {"topic": "Mini project polish", "hours": 4, "task": "Add basic styling and error handling to your app."},
        ],
        "opportunity_ready": [
            {"topic": "Debugging and browser dev tools", "hours": 2, "task": "Intentionally break your app, then fix it using the console/debugger."},
            {"topic": "Mock interview: explain your project's architecture", "hours": 2, "task": "Practice a 2-minute walkthrough of your app."},
        ],
    },
    "typescript": {
        "foundations": [
            {"topic": "Types, variables, and type inference", "hours": 2, "task": "Convert 3 small JavaScript scripts to TypeScript."},
        ],
        "interview": [
            {"topic": "Functions: typed parameters, optional/default params", "hours": 2, "task": "Practice writing 5 typed function signatures.", "practice": "Explain the difference between `unknown` and `any`."},
            {"topic": "Interfaces and type aliases", "hours": 2, "task": "Create typed models for a small application."},
        ],
        "project": [
            {"topic": "Generics", "hours": 3, "task": "Write 3 generic utility functions (e.g. a typed filter helper)."},
            {"topic": "Mini project: add TypeScript to an existing small app", "hours": 6, "task": "Migrate a small JS project (or write a new small one) fully typed."},
        ],
        "opportunity_ready": [
            {"topic": "tsconfig basics and common compiler errors", "hours": 2, "task": "Intentionally trigger and fix 5 common TS compiler errors."},
            {"topic": "Interview prep: typing trade-offs", "hours": 2, "task": "Practice explaining when you'd use `interface` vs `type`."},
        ],
    },
    "react": {
        "foundations": [
            {"topic": "Components, JSX, and props", "hours": 3, "task": "Build 3 small reusable presentational components."},
            {"topic": "State with useState", "hours": 3, "task": "Build a counter and a small form using state."},
        ],
        "interview": [
            {"topic": "useEffect and the component lifecycle", "hours": 4, "task": "Build a component that fetches data on mount."},
            {"topic": "Common interview questions (keys, re-renders, lifting state)", "hours": 3, "task": "Practice explaining why React needs `key` props in lists."},
        ],
        "project": [
            {"topic": "Routing and multi-page apps", "hours": 4, "task": "Add 2-3 routes to a small app."},
            {"topic": "Mini project: a small multi-component app", "hours": 8, "task": "Build a small app end-to-end (e.g. a notes app) with at least 3 components."},
        ],
        "opportunity_ready": [
            {"topic": "Basic performance/debugging (React DevTools)", "hours": 2, "task": "Use React DevTools to inspect your app's component tree and props."},
            {"topic": "Mock interview: walk through your project's component structure", "hours": 2, "task": "Practice a 2-minute explanation of your app's architecture."},
        ],
    },
    "html": {
        "foundations": [
            {"topic": "Semantic HTML structure", "hours": 2, "task": "Rebuild a simple webpage layout using semantic tags."},
        ],
        "interview": [
            {"topic": "Forms and accessibility basics", "hours": 2, "task": "Build an accessible contact form."},
        ],
        "project": [
            {"topic": "Mini project: a complete static page", "hours": 4, "task": "Build a full one-page site (landing page) with proper structure."},
        ],
        "opportunity_ready": [
            {"topic": "Validation and cross-browser basics", "hours": 1, "task": "Run your page through an HTML validator and fix any issues."},
        ],
    },
    "css": {
        "foundations": [
            {"topic": "Box model, selectors, and basic layout", "hours": 3, "task": "Style a simple page from scratch."},
        ],
        "interview": [
            {"topic": "Flexbox", "hours": 3, "task": "Rebuild 3 common layouts (navbar, card grid, centered content) with flexbox."},
        ],
        "project": [
            {"topic": "CSS Grid and responsive design", "hours": 4, "task": "Make your project's layout responsive across 3 screen sizes."},
            {"topic": "Mini project: polish a full page", "hours": 4, "task": "Take an existing unstyled page and fully style it."},
        ],
        "opportunity_ready": [
            {"topic": "Common interview questions (specificity, box-sizing)", "hours": 2, "task": "Practice explaining CSS specificity with 3 examples."},
        ],
    },
    "machine learning": {
        "foundations": [
            {"topic": "Core concepts: supervised vs unsupervised, train/test split", "hours": 3, "task": "Explain these concepts in your own words with an example each."},
            {"topic": "Linear & logistic regression", "hours": 4, "task": "Train both models on a small sample dataset using scikit-learn."},
        ],
        "interview": [
            {"topic": "Evaluation metrics (accuracy, precision/recall, RMSE)", "hours": 3, "task": "Compute and compare 4 metrics on your trained models.", "practice": "Practice explaining the precision/recall trade-off."},
            {"topic": "Overfitting, cross-validation, regularization", "hours": 4, "task": "Run k-fold cross-validation on your regression model."},
        ],
        "project": [
            {"topic": "Feature engineering and a tree-based model", "hours": 5, "task": "Train a random forest on a slightly larger dataset with engineered features."},
            {"topic": "Mini project: an end-to-end small ML pipeline", "hours": 8, "task": "Build a notebook that goes from raw data to a trained, evaluated model."},
        ],
        "opportunity_ready": [
            {"topic": "Communicating results (a short write-up)", "hours": 2, "task": "Write a half-page summary of your project's approach and results."},
            {"topic": "Mock interview: explain your model's trade-offs", "hours": 2, "task": "Practice justifying your model choice and its limitations."},
        ],
    },
    "deep learning": {
        "foundations": [
            {"topic": "Neural network basics (neurons, layers, activation functions)", "hours": 4, "task": "Sketch and explain a simple 2-layer network by hand."},
        ],
        "interview": [
            {"topic": "Backpropagation and gradient descent intuition", "hours": 4, "task": "Explain backprop in your own words with a tiny worked example.", "practice": "Review common activation functions and when to use them."},
        ],
        "project": [
            {"topic": "Build a simple network with a framework (TensorFlow/PyTorch)", "hours": 6, "task": "Train a basic image classifier on a small dataset (e.g. MNIST)."},
            {"topic": "Mini project: tune and evaluate your model", "hours": 6, "task": "Try 2-3 architecture/hyperparameter changes and compare results."},
        ],
        "opportunity_ready": [
            {"topic": "Common pitfalls (overfitting, vanishing gradients) and fixes", "hours": 3, "task": "Diagnose one issue in your model and apply a fix (e.g. dropout, batch norm)."},
        ],
    },
    "docker": {
        "foundations": [
            {"topic": "Containers vs VMs, images vs containers", "hours": 2, "task": "Run and explore 2 existing images (e.g. nginx, postgres)."},
        ],
        "interview": [
            {"topic": "Writing a Dockerfile", "hours": 3, "task": "Containerize a small app you've already built."},
        ],
        "project": [
            {"topic": "docker-compose for multi-container apps", "hours": 4, "task": "Run a small app + database together with docker-compose."},
            {"topic": "Mini project: containerize and document a full app", "hours": 4, "task": "Write a README explaining how to build and run your containerized app."},
        ],
        "opportunity_ready": [
            {"topic": "Common interview questions (volumes, networking basics)", "hours": 2, "task": "Practice explaining the difference between a volume and a bind mount."},
        ],
    },
    "kubernetes": {
        "foundations": [
            {"topic": "Prerequisite check: container/Docker basics", "hours": 2, "task": "Make sure you can build and run a Docker container before continuing."},
            {"topic": "Kubernetes architecture and Pods", "hours": 3, "task": "Run a single pod on a local cluster (e.g. minikube/kind) and inspect it."},
        ],
        "interview": [
            {"topic": "Deployments and Services", "hours": 4, "task": "Deploy an app with a Deployment + Service and scale it manually."},
        ],
        "project": [
            {"topic": "ConfigMaps and Secrets", "hours": 3, "task": "Externalize config for your app using a ConfigMap."},
            {"topic": "Mini project: deploy a small multi-pod app", "hours": 6, "task": "Deploy an app with 2+ pods, a service, and a ConfigMap."},
        ],
        "opportunity_ready": [
            {"topic": "Scaling, debugging, and reading logs", "hours": 3, "task": "Intentionally break your deployment, then diagnose it using `kubectl logs`/`describe`."},
            {"topic": "Common interview questions", "hours": 2, "task": "Practice explaining Pods vs Deployments vs Services out loud."},
        ],
    },
    "git": {
        "foundations": [
            {"topic": "Core workflow: add, commit, push, pull", "hours": 2, "task": "Make 5 commits with clear messages on a practice repo."},
        ],
        "interview": [
            {"topic": "Branching and merging", "hours": 2, "task": "Create a feature branch, make changes, and merge it back."},
        ],
        "project": [
            {"topic": "Resolving merge conflicts", "hours": 2, "task": "Intentionally create and resolve a merge conflict."},
        ],
        "opportunity_ready": [
            {"topic": "Common interview questions (rebase vs merge)", "hours": 1, "task": "Practice explaining the difference between rebase and merge."},
        ],
    },
    "statistics": {
        "foundations": [
            {"topic": "Descriptive statistics (mean, median, std dev)", "hours": 2, "task": "Compute these for a sample dataset by hand and with code."},
        ],
        "interview": [
            {"topic": "Probability basics and distributions", "hours": 3, "task": "Solve 5 basic probability problems."},
        ],
        "project": [
            {"topic": "Hypothesis testing (t-test, chi-square)", "hours": 4, "task": "Run a t-test comparing two groups in a sample dataset."},
            {"topic": "Mini project: a small statistical analysis write-up", "hours": 4, "task": "Analyze a sample dataset and write a short summary of your findings."},
        ],
        "opportunity_ready": [
            {"topic": "Common interview questions (p-values, confidence intervals)", "hours": 2, "task": "Practice explaining a p-value in plain language."},
        ],
    },
    "data visualization": {
        "foundations": [
            {"topic": "Chart types and when to use each", "hours": 2, "task": "Pick the right chart type for 5 different sample questions."},
        ],
        "interview": [
            {"topic": "Building charts with a library (matplotlib/seaborn)", "hours": 3, "task": "Recreate 4 chart types from a sample dataset."},
        ],
        "project": [
            {"topic": "Mini project: a small visual report", "hours": 5, "task": "Build a 3-4 chart report telling one clear story from a dataset."},
        ],
        "opportunity_ready": [
            {"topic": "Design basics (labeling, avoiding misleading charts)", "hours": 2, "task": "Review your charts for clarity and fix any misleading elements."},
        ],
    },
    "java": {
        "foundations": [
            {"topic": "Syntax, classes, and objects", "hours": 4, "task": "Write 3 small classes modeling a simple domain (e.g. a library system)."},
        ],
        "interview": [
            {"topic": "Collections (List, Map, Set)", "hours": 4, "task": "Solve 6 problems using Java's collection types."},
        ],
        "project": [
            {"topic": "OOP principles in practice (inheritance, interfaces)", "hours": 5, "task": "Refactor your classes to use inheritance/interfaces appropriately."},
            {"topic": "Mini project: a small console application", "hours": 6, "task": "Build a complete small console app (e.g. a basic inventory tracker)."},
        ],
        "opportunity_ready": [
            {"topic": "Common interview questions (equals/hashCode, exceptions)", "hours": 2, "task": "Practice explaining why you'd override equals() and hashCode() together."},
        ],
    },
}

# Soft prerequisite hints - shown as a note, never silently assumed.
PREREQUISITES = {
    "react": "javascript",
    "typescript": "javascript",
    "kubernetes": "docker",
    "deep learning": "machine learning",
    "spring boot": "java",
    "power bi": "excel",
    "pandas": "python",
    "scikit-learn": "python",
    "tensorflow": "python",
    "pytorch": "python",
}

GENERIC_STAGES = {
    "foundations": [
        {"topic": "Core concepts and terminology", "hours": 4, "task": "Summarize the core concepts in your own words."},
        {"topic": "Basic hands-on practice", "hours": 4, "task": "Complete 3-5 small guided exercises."},
    ],
    "interview": [
        {"topic": "Common interview questions and patterns", "hours": 4, "task": "Research and answer 5 common interview questions on this skill."},
    ],
    "project": [
        {"topic": "Relevant tools/APIs deep dive", "hours": 5, "task": "Explore the most commonly used tools/libraries for this skill."},
        {"topic": "Mini project", "hours": 8, "task": "Build one small project that uses this skill end-to-end."},
    ],
    "opportunity_ready": [
        {"topic": "Skills specifically relevant to your target opportunities", "hours": 4, "task": "Review the specific requirements from opportunities needing this skill."},
        {"topic": "Mock interview / review session", "hours": 2, "task": "Practice explaining what you built and why."},
    ],
}


def _skill_key(skill: str) -> str:
    return normalize_skill(skill)


def get_topics_for_goal(skill: str, goal: str):
    """
    Return (topics, is_curated) for `skill` at the given `goal` level,
    cumulative through GOAL_ORDER up to and including `goal`.
    `is_curated` is False when falling back to the generic structure -
    the UI should disclose this rather than presenting it as a
    hand-designed curriculum for that specific skill.
    """
    key = _skill_key(skill)
    goal = goal if goal in GOAL_ORDER else "foundations"
    levels = GOAL_ORDER[: GOAL_ORDER.index(goal) + 1]

    source = SKILL_ROADMAPS.get(key)
    is_curated = source is not None
    if source is None:
        source = GENERIC_STAGES

    topics: List[Dict] = []
    for level in levels:
        topics.extend(source.get(level, []))
    return topics, is_curated


def get_skill_options(student, opportunities: List[Dict], top_n: int = 10) -> List[Dict]:
    """
    The dropdown's contents: the student's actual missing/high-priority
    skills, reusing the existing opportunity-gap ranking
    (recommendation.recommend_skills_to_learn) rather than any new
    ranking logic. Each entry already carries `opportunity_count`.
    """
    return recommend_skills_to_learn(student, opportunities, top_n=top_n)


def get_relevant_opportunities(skill: str, opportunities: List[Dict]) -> List[Dict]:
    """Opportunities (from the EXISTING dataset only) that list this skill as required or preferred."""
    key = _skill_key(skill)
    relevant = []
    for opp in opportunities:
        required = set(normalize_skill_list(opp.get("required_skills", [])))
        preferred = set(normalize_skill_list(opp.get("preferred_skills", [])))
        if key in required or key in preferred:
            relevant.append(opp)
    return relevant


def get_nearest_deadline(skill: str, student, opportunities: List[Dict]) -> Optional[str]:
    """
    The nearest REAL deadline (ISO date string) among opportunities that
    require this skill, are not expired/closed, and the student is not
    flatly NOT_ELIGIBLE for. Returns None if there is no such deadline -
    never fabricated.
    """
    from src.eligibility import NOT_ELIGIBLE

    relevant = get_relevant_opportunities(skill, opportunities)
    candidate_dates = []
    for opp in relevant:
        if opp.get("status") in ("EXPIRED", "CLOSED"):
            continue
        if not opp.get("deadline"):
            continue
        match = compute_match(student, opp)
        if match["eligibility_status"] == NOT_ELIGIBLE:
            continue
        try:
            candidate_dates.append(datetime.fromisoformat(opp["deadline"]).date())
        except ValueError:
            continue

    return min(candidate_dates).isoformat() if candidate_dates else None


def assess_deadline_feasibility(days_required: int, deadline_str: Optional[str]) -> Dict:
    """
    Compare the roadmap's required study days against a real deadline (if
    any) and return an honest, non-overpromising assessment.
    """
    if not deadline_str:
        return {
            "status": "no_deadline",
            "available_days": None,
            "message": "No verified deadline available. You can follow this roadmap at your own pace.",
        }

    try:
        deadline = datetime.fromisoformat(deadline_str).date()
    except ValueError:
        return {
            "status": "no_deadline",
            "available_days": None,
            "message": "No verified deadline available. You can follow this roadmap at your own pace.",
        }

    available_days = (deadline - date.today()).days

    if available_days >= days_required:
        return {
            "status": "achievable",
            "available_days": available_days,
            "message": (
                f"You have approximately {available_days} days before the deadline. "
                f"Estimated learning time is {days_required} study days. "
                f"This roadmap is realistically achievable if you maintain your planned study schedule."
            ),
        }

    return {
        "status": "not_achievable",
        "available_days": available_days,
        "message": (
            f"\u26a0\ufe0f You have approximately {max(available_days, 0)} days before the deadline, "
            f"but this roadmap is estimated to take {days_required} study days. "
            f"This skill may not be realistically achievable before the deadline at your current study time. "
            f"Prioritize the minimum practical topics that could improve your match rather than "
            f"attempting the entire skill."
        ),
    }


def build_daily_schedule(topics: List[Dict], hours_per_day: float) -> List[Dict]:
    """
    Pack topics into day-sized chunks without splitting a topic across
    days (a topic longer than the daily budget gets its own, longer day).
    Returns a list of {day, topics, hours, tasks, practice}.
    """
    days: List[Dict] = []
    current_topics: List[Dict] = []
    current_hours = 0.0

    def flush():
        if not current_topics:
            return
        days.append({
            "day": len(days) + 1,
            "topics": [t["topic"] for t in current_topics],
            "hours": round(current_hours, 2),
            "tasks": [t["task"] for t in current_topics if t.get("task")],
            "practice": [t["practice"] for t in current_topics if t.get("practice")],
        })

    for topic in topics:
        t_hours = topic["hours"]
        if current_topics and current_hours + t_hours > hours_per_day:
            flush()
            current_topics, current_hours = [], 0.0
        current_topics.append(topic)
        current_hours += t_hours

    flush()
    return days


def build_roadmap(skill: str, goal: str, hours_per_day: float, student, opportunities: List[Dict]) -> Dict:
    """
    Build the full roadmap for one skill: curriculum, daily schedule,
    deadline feasibility, opportunity connection, and next-skill
    suggestions. This is the single entry point src/roadmap_ui.py calls
    after the student clicks "Generate Personalized Roadmap".
    """
    topics, is_curated = get_topics_for_goal(skill, goal)
    total_hours = sum(t["hours"] for t in topics)
    daily_schedule = build_daily_schedule(topics, hours_per_day)
    days_required = len(daily_schedule) or (math.ceil(total_hours / hours_per_day) if hours_per_day else 0)

    relevant_opportunities = get_relevant_opportunities(skill, opportunities)
    nearest_deadline = get_nearest_deadline(skill, student, opportunities)
    feasibility = assess_deadline_feasibility(days_required, nearest_deadline)

    prereq_skill = PREREQUISITES.get(_skill_key(skill))
    prereq_note = None
    if prereq_skill and prereq_skill not in set(normalize_skill_list(getattr(student, "skills", []))):
        prereq_note = f"Before starting this topic, you may want to review {prereq_skill.title()} basics."

    next_skills = [
        s for s in get_skill_options(student, opportunities, top_n=6)
        if _skill_key(s["skill"]) != _skill_key(skill)
    ][:3]

    return {
        "skill": skill,
        "goal": goal,
        "goal_label": GOAL_LABELS.get(goal, goal.title()),
        "is_curated": is_curated,
        "total_hours": total_hours,
        "hours_per_day": hours_per_day,
        "days_required": days_required,
        "daily_schedule": daily_schedule,
        "prereq_note": prereq_note,
        "relevant_opportunities": relevant_opportunities,
        "nearest_deadline": nearest_deadline,
        "deadline_feasibility": feasibility,
        "next_skills": next_skills,
    }


@dataclass
class _ShadowProfile:
    """
    Minimal stand-in used only to simulate "what if this skill were
    learned" without mutating the real student profile. Carries whatever
    attributes eligibility/matching need by copying them from the real
    profile, so eligibility checks (degree/branch/year/semester/CGPA)
    behave identically to the original - only `skills` changes.
    """
    name: str = None
    degree: str = None
    branch: str = None
    graduation_year: int = None
    semester: int = None
    cgpa: float = None
    skills: list = None


def _with_skill_added(student, skill: str):
    shadow = _ShadowProfile(
        name=getattr(student, "name", None),
        degree=getattr(student, "degree", None),
        branch=getattr(student, "branch", None),
        graduation_year=getattr(student, "graduation_year", None),
        semester=getattr(student, "semester", None),
        cgpa=getattr(student, "cgpa", None),
        skills=list(getattr(student, "skills", [])) + [skill],
    )
    return shadow


def compute_opportunity_impact(student, opportunities: List[Dict], skill: str) -> Dict:
    """
    Re-runs the EXISTING matching logic (compute_match) twice - once with
    the student's real profile, once with `skill` hypothetically added -
    against only the opportunities that actually require/prefer this
    skill. Never fabricates improvement: if compute_match doesn't show a
    change, this function won't report one.

    Eligibility (degree/branch/graduation year/semester/CGPA/deadline) is
    computed by src/eligibility.py, which does not look at skills at all
    - so eligibility_status is identical before and after by construction.
    This function makes that explicit rather than implying a skill can
    change eligibility.
    """
    relevant = get_relevant_opportunities(skill, opportunities)
    shadow = _with_skill_added(student, skill)

    before = [compute_match(student, opp) for opp in relevant]
    after = [compute_match(shadow, opp) for opp in relevant]

    before_full_coverage = sum(1 for b in before if not b["missing_skills"])
    after_full_coverage = sum(1 for a in after if not a["missing_skills"])

    pairs = []
    for b, a in zip(before, after):
        pairs.append({
            "company": b["company"],
            "role": b["role"],
            "before_score": b["match_score"],
            "after_score": a["match_score"],
            "before_missing": b["missing_skills"],
            "after_missing": a["missing_skills"],
            "eligibility_status": b["eligibility_status"],  # identical before/after - see docstring
        })

    return {
        "relevant_count": len(relevant),
        "before_full_coverage_count": before_full_coverage,
        "after_full_coverage_count": after_full_coverage,
        "pairs": pairs,
        "note": (
            "Based on the current matching model. Eligibility (degree, branch, graduation year, "
            "semester, CGPA, deadline) is evaluated separately and is not changed by learning a "
            "skill alone - an opportunity you're NOT_ELIGIBLE for stays that way unless those "
            "underlying requirements change."
        ),
    }


def progress_status(completed: int, total: int) -> str:
    if total == 0:
        return "NOT_STARTED"
    if completed == 0:
        return "NOT_STARTED"
    if completed >= total:
        return "COMPLETED"
    return "IN_PROGRESS"


def progress_summary(daily_schedule: List[Dict], completed_days: Set[int]) -> Dict:
    """Progress stats for the UI's checkboxes + progress bar."""
    total = len(daily_schedule)
    completed = len([d for d in daily_schedule if d["day"] in completed_days])
    remaining_hours = sum(d["hours"] for d in daily_schedule if d["day"] not in completed_days)
    return {
        "completed": completed,
        "total": total,
        "status": progress_status(completed, total),
        "remaining_hours": round(remaining_hours, 2),
    }
