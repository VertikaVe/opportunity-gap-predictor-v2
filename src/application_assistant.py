"""
application_assistant.py
------------------------
Opens official internship application pages and
automatically fills commonly recognized profile fields.

The user remains responsible for reviewing and submitting applications.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def validate_application_url(url):
    """Allow only valid HTTP/HTTPS application URLs."""

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid application URL.")

    return url


def launch_application_assistant(url, profile):
    """
    Launch browser automation in a separate process so
    Streamlit remains responsive.
    """

    url = validate_application_url(url)

    profile_data = (
        profile.to_dict()
        if hasattr(profile, "to_dict")
        else dict(profile)
    )

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--url",
        url,
        "--profile-json",
        json.dumps(profile_data),
    ]

    return subprocess.Popen(
        command,
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP
            if sys.platform == "win32"
            else 0
        ),
    )


def _field_value(field_description, profile):
    """Identify a profile value from common form field names."""

    text = field_description.lower()

    patterns = {
        "name": r"\b(name|full.?name|first.?name)\b",
        "email": r"\b(email|e-mail)\b",
        "phone": r"\b(phone|mobile|telephone|contact.?number)\b",
        "college": r"\b(college|university|institution|school)\b",
        "degree": r"\b(degree|qualification|education)\b",
        "branch": r"\b(branch|major|specialization|discipline)\b",
        "graduation_year": r"\b(graduation.?year|passing.?year)\b",
        "cgpa": r"\b(cgpa|gpa|grade.?point)\b",
    }

    for field, pattern in patterns.items():
        if re.search(pattern, text):
            value = profile.get(field)

            if value is not None and value != "":
                return str(value)

    return None


def _run_browser(url, profile):
    """Open the application page and fill recognized fields."""

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(2000)

        filled = 0

        fields = page.locator(
            "input:not([type='hidden']):not([type='password']), textarea"
        )

        for index in range(fields.count()):

            field = fields.nth(index)

            try:
                if not field.is_visible() or not field.is_enabled():
                    continue

                field_type = (
                    field.get_attribute("type") or ""
                ).lower()

                if field_type in (
                    "submit", "button", "file", "checkbox",
                    "radio", "reset", "image"
                ):
                    continue

                description = " ".join([
                    field.get_attribute("name") or "",
                    field.get_attribute("id") or "",
                    field.get_attribute("placeholder") or "",
                    field.get_attribute("aria-label") or "",
                    field.get_attribute("autocomplete") or "",
                ])

                value = _field_value(description, profile)

                if value:
                    field.fill(value)
                    filled += 1

            except Exception:
                continue

        print(f"Application page opened: {url}")
        print(f"Recognized fields filled: {filled}")
        print("Please review every field before submitting.")
        print("The assistant will NOT submit the application.")

        # Keep the browser open until the user closes it.
        page.wait_for_event("close", timeout=0)

        browser.close()


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument("--url", required=True)
    parser.add_argument("--profile-json", required=True)

    args = parser.parse_args()

    try:
        _run_browser(
            args.url,
            json.loads(args.profile_json),
        )
    except Exception as error:
        print(f"Application assistant error: {error}")