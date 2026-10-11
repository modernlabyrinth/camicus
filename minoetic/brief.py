"""Derive a brief, then independently check its coverage and copied facts."""
from .contracts import STATES, validate_brief_shape
from .models import Check, JsonObject, Problem, Project, Tasks, stamp


def build_brief(project: Project, tasks: Tasks) -> JsonObject:
    counts = {state: sum(t.state == state for t in tasks.tasks) for state in STATES}
    return dict(project_id=project.project_id, project_summary=project.summary,
                source_as_of=dict(project=stamp(project.as_of), tasks=stamp(tasks.as_of)),
                task_counts=dict(total=len(tasks.tasks), **counts),
                blocked_tasks=[dict(id=t.id, title=t.title) for t in sorted(tasks.tasks, key=lambda t: t.id)
                               if t.state == "blocked"])


def verify_brief(brief: JsonObject, project: Project, tasks: Tasks) -> Check:
    failure = Check("brief_invariants", "failed", "brief_mismatch")
    try:
        validate_brief_shape(brief)
    except (Problem, TypeError):
        return failure
    if (brief["project_id"] != project.project_id or project.project_id != tasks.project_id
            or brief["project_summary"] != project.summary
            or brief["source_as_of"] != {"project": stamp(project.as_of), "tasks": stamp(tasks.as_of)}):
        return failure
    # This verifier does not call the renderer or trust its counts.
    remaining = dict(brief["task_counts"])
    blocked = {row["id"]: row["title"] for row in brief["blocked_tasks"]}
    for task in tasks.tasks:
        remaining["total"] -= 1
        remaining[task.state] -= 1
        if task.state == "blocked" and blocked.pop(task.id, None) != task.title:
            return failure
    if any(remaining.values()) or blocked:
        return failure
    return Check("brief_invariants", "passed", "ok")
