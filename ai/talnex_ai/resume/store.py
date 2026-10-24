"""Saves what the resume reader found. Safe to run twice: a project already saved (same name) is updated, not added again."""
from __future__ import annotations

import json

from psycopg_pool import ConnectionPool

from talnex_ai.resume.reader import ResumeRead


def save_resume(pool: ConnectionPool, candidate_id: str, read: ResumeRead) -> list[str]:
    """Save the projects and coding handles; return the candidate project ids in resume order.

    Coding handles the recruiter typed in the form are never overwritten by what the resume says.
    """
    ids: list[str] = []
    with pool.connection() as conn:
        for project in read.projects:
            row = conn.execute(
                "SELECT id::text FROM candidate_projects WHERE candidate_id = %s::uuid AND lower(name) = lower(%s)",
                (candidate_id, project.name)).fetchone()
            if row:
                conn.execute(
                    """UPDATE candidate_projects SET bullets = %s, live_url = %s, repo_url = %s, video_url = %s
                        WHERE id = %s::uuid""",
                    (list(project.bullets), project.live_url, project.repo_url, project.video_url, row[0]))
                ids.append(row[0])
            else:
                ids.append(conn.execute(
                    """INSERT INTO candidate_projects (candidate_id, name, bullets, live_url, repo_url, video_url)
                       VALUES (%s::uuid, %s, %s, %s, %s, %s) RETURNING id::text""",
                    (candidate_id, project.name, list(project.bullets), project.live_url, project.repo_url,
                     project.video_url)).fetchone()[0])
        if read.coding_handles:
            # resume handles first, then what the recruiter typed wins
            conn.execute("UPDATE candidates SET coding_handles = %s::jsonb || coding_handles, updated_at = now() WHERE id = %s::uuid",
                         (json.dumps(read.coding_handles), candidate_id))
        if read.profile_links:
            conn.execute("UPDATE candidates SET profile_links = %s::jsonb || profile_links WHERE id = %s::uuid",
                         (json.dumps(read.profile_links), candidate_id))
        if read.coding_links:
            conn.execute("UPDATE candidates SET coding_links = %s::jsonb || coding_links WHERE id = %s::uuid",
                         (json.dumps(read.coding_links), candidate_id))
    return ids
