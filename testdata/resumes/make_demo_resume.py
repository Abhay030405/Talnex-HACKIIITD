"""Builds the demo resume: Arnav Raj (on the TalNex team), whose four projects are our planted apps, for showing
the recruiter flow end to end. The repos are on his GitHub, so the name and the GitHub account match.

Run from the repository root (needs reportlab, from the ai dev extras):
    python testdata/resumes/make_demo_resume.py

It writes testdata/resumes/demo_resume.pdf. What TalNex should find:
- TinyTools: every claim works.
- NoteBox: adding and searching work, pinning does nothing.
- ShelfMate: accounts, books, status and ratings work; the CSV export and the reading goal do not.
- CaptionIt: the pages work, the AI caption never appears.
Bullets are plain dashes so the text reads back without unknown glyphs.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
OUT = HERE / "demo_resume.pdf"

NAME = "Arnav Raj"
LABEL = "Demo resume for TalNex: the projects below are TalNex test apps"
CONTACT = "Email: arnav.demo@talnex.test | GitHub: github.com/arnavraj-7 | New Delhi, India"
EDUCATION = "B.Tech in Computer Science and Engineering, Example Institute of Technology, 2022 - 2026 | CGPA 8.4"
SUMMARY = ("Final-year student who builds small, useful web apps end to end: plain JavaScript front ends, "
           "Node.js serverless APIs and deployments on Vercel.")

REPO = "https://github.com/arnavraj-7/talnex-planted-"
PROJECTS = [
    ("TinyTools - everyday web tools", "https://talnex-honest.vercel.app", REPO + "honest", [
        "Added guest sign-in so people can start using the tools without creating an account.",
        "Built a currency converter between US dollars, euros, pounds and Indian rupees that shows a clear "
        "message for an empty, non-numeric or negative amount.",
        "Built a todo list where you can add, tick off and delete items, and it is still there after a page reload.",
    ]),
    ("ShelfMate - reading tracker", "https://talnex-shelfmate.vercel.app", REPO + "shelfmate", [
        "Built email and password accounts with sign-up, sign-in and sign-out; each reader sees only their own shelf.",
        "Add, edit, search and delete books, mark them Want to read, Reading or Finished, and rate finished books 1 to 5.",
        "Added a one-click Export CSV of the whole shelf and a yearly reading goal with a progress bar.",
    ]),
    ("NoteBox - quick notes", "https://talnex-partly-works.vercel.app", REPO + "partly-works", [
        "Built a notes page where you add notes and search them as you type.",
        "Added pinning, so a pinned note moves to the top of the list with a Pinned label.",
    ]),
    ("CaptionIt - AI photo captions", "https://talnex-fake-claim.vercel.app", REPO + "fake-claim", [
        "Built an AI captioning app: upload a photo and it writes a caption describing it.",
    ]),
]

SKILLS = "JavaScript, Node.js, HTML, CSS, REST APIs, Vercel serverless functions, Git, SQL, Python"


def build(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setTitle("Demo resume - Arnav Raj")
    pdf.setAuthor("TalNex demo data")
    width, height = A4
    left = 50
    wrap = width - 2 * left - 10
    y = height - 60

    def line(text: str, font: str = "Helvetica", size: int = 10, gap: int = 15) -> None:
        nonlocal y
        pdf.setFont(font, size)
        pdf.drawString(left, y, text)
        y -= gap

    def para(text: str, prefix: str = "", gap: int = 14) -> None:
        first, *rest = simpleSplit(text, "Helvetica", 10, wrap)
        line(prefix + first, gap=gap)
        for more in rest:
            line(" " * len(prefix) + more, gap=gap)

    def heading(text: str) -> None:
        nonlocal y
        y -= 4
        line(text, "Helvetica-Bold", 12, 6)
        pdf.setLineWidth(0.6)
        pdf.line(left, y, width - left, y)
        y -= 14

    line(NAME, "Helvetica-Bold", 20, 16)
    line(LABEL, "Helvetica-Oblique", 9, 14)
    line(CONTACT, gap=18)
    para(SUMMARY)

    heading("Education")
    line(EDUCATION, gap=16)

    heading("Projects")
    for name, live, repo, bullets in PROJECTS:
        line(name, "Helvetica-Bold", 10.5, 13)
        line(f"Live: {live} | Code: {repo}", "Helvetica", 9, 13)
        for bullet in bullets:
            para(bullet, prefix="- ")
        y -= 6

    heading("Skills")
    para(SKILLS)
    pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    build(OUT)
    print(f"wrote {OUT}")
