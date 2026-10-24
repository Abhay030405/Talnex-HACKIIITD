"""Builds the test resume: a made-up fresher with the planted TinyTools app and two other projects.

Run from the repository root (needs reportlab, from the ai dev extras):
    python testdata/resumes/make_test_resume.py

It writes testdata/resumes/test_resume.pdf and the same file to testdata/known_answers/, where the test
agent may upload it. Bullets are plain dashes so the text reads back without unknown glyphs.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
OUT = HERE / "test_resume.pdf"
COPY = HERE.parent / "known_answers" / "test_resume.pdf"

NAME = "Asha Verma"
CONTACT = "Email: asha.verma@talnex.test | GitHub: github.com/talnex-fixture"

PROJECTS = [
    ("TinyTools", "https://talnex-honest.vercel.app", "https://github.com/talnex-fixture/tinytools", [
        "Added guest sign-in so people can start using the tools without creating an account.",
        "Built a currency converter between US dollars, euros, pounds and Indian rupees that shows a clear message for an empty, "
        "non-numeric or negative amount.",
        "Added a todo list that is still there after a page reload.",
        "Improved conversion speed by 40% by caching the exchange rates.",
    ]),
    ("NoteNest", "https://notenest-demo.example.invalid", "https://github.com/talnex-fixture/notenest", [
        "Built a notes app where users can pin and search notes.",
    ]),
    ("ChatSummarizer", None, "https://github.com/talnex-fixture/chat-summarizer", [
        "Wrote a command line tool that summarises long chat exports into short notes.",
    ]),
]

SKILLS = "Skills: JavaScript, TypeScript, React, Python, SQL, Git"
CODING = "Coding: Codeforces: talnex_fixture_cf | LeetCode: talnex_fixture_lc | CodeChef: talnex_fixture_cc"
EDUCATION = "Education: B.Tech in Computer Science, Example Institute of Technology, 2022 - 2026"


def build(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setTitle("Test resume")
    pdf.setAuthor("TalNex test data")
    width, height = A4
    left = 50
    y = height - 60

    def line(text: str, font: str = "Helvetica", size: int = 10, gap: int = 15) -> None:
        nonlocal y
        pdf.setFont(font, size)
        pdf.drawString(left, y, text)
        y -= gap

    line(NAME, "Helvetica-Bold", 18, 22)
    line(CONTACT)
    line(EDUCATION, gap=24)

    line("Projects", "Helvetica-Bold", 13, 18)
    for name, live, repo, bullets in PROJECTS:
        parts = [name] + ([f"Live: {live}"] if live else []) + [f"Code: {repo}"]
        line(" | ".join(parts), "Helvetica-Bold", 10)
        for bullet in bullets:
            first, *rest = simpleSplit(bullet, "Helvetica", 10, width - 2 * left - 10)
            line(f"- {first}", gap=14)
            for more in rest:
                line(f"  {more}", gap=14)
        y -= 6

    line(SKILLS)
    line(CODING)
    pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    build(OUT)
    COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT, COPY)
    print(f"wrote {OUT} and {COPY}")
