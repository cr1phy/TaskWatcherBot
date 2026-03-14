from typing import Any

from .models import Group, GroupStudent, Journal, Student, Task, Work


def parse_groups(data: list[dict[str, Any]]) -> list[Group]:
    return [
        Group(
            id=g["id"],
            name=g["name"],
            students=[
                GroupStudent(
                    id=s["id"],
                    first_name=s["first_name"],
                    last_name=s["last_name"],
                    middle_name=s.get("middle_name"),
                )
                for s in g["students"]["data"]
            ],
        )
        for g in data
        if "Группа" in g["name"]
    ]


def parse_works(works_data: list[Any] | dict[str, Any]) -> dict[int, Work]:
    works: dict[int, Work] = {}

    def _make_work(task_id: int, wl: list[dict[str, Any]]) -> Work:
        best = max(wl, key=lambda w: w["ball"] or 0)
        return Work(
            task_id=task_id,
            score=best["ball"] or 0,
            maximum_score=best["max_ball"] or 0,
            status=best["status"],
        )

    if isinstance(works_data, list):
        by_task: dict[int, list[dict[str, Any]]] = {}
        for w in works_data:
            by_task.setdefault(w["task_id"], []).append(w)
        for task_id, wl in by_task.items():
            works[task_id] = _make_work(task_id, wl)
    else:
        for task_id_str, wl in works_data.items():
            if wl:
                tid = int(task_id_str)
                works[tid] = _make_work(tid, wl)
    return works


def parse_journal(data: dict[str, Any]) -> Journal:
    j = data["journal"]
    return Journal(
        id=j["group"]["id"],
        name=j["group"]["name"],
        tasks=[
            Task(id=t["id"], name=t["name"], maximum_score=t.get("max_ball", 0))
            for t in j["tasks"]
        ],
        students=[
            Student(
                id=s.get("id", 0),
                name=s["name"],
                works=parse_works(s["works"]),
                count=s["count"],
                avg=s["avg"],
            )
            for s in j["data"]
        ],
    )


def apply_max_balls(journal: Journal, max_ball_map: dict[int, int]) -> None:
    student_max: dict[int, int] = {}
    for s in journal.students:
        for tid, w in s.works.items():
            if w.maximum_score > student_max.get(tid, 0):
                student_max[tid] = w.maximum_score

    for task in journal.tasks:
        api_mb = max_ball_map.get(task.id, 0)
        stud_mb = student_max.get(task.id, 0)
        if api_mb > 0:
            task.maximum_score = api_mb
        elif stud_mb > 0:
            task.maximum_score = stud_mb
        else:
            task.maximum_score = 0


def parse_task_max_ball(detail: dict[str, Any]) -> int:
    if not detail:
        return 0
    fields = detail.get("task", detail).get("fields", [])
    if not fields:
        return 0

    total = sum(
        int(f.get("max_ball") or 0)
        for f in fields
        if isinstance(f.get("max_ball"), (int, float))
    )
    if total > 0:
        return total

    total_criteria = sum(
        int(crit.get("max_ball") or 0)
        for f in fields
        for crit in f.get("criteria", [])
        if isinstance(crit.get("max_ball"), (int, float))
    )
    if total_criteria > 0:
        return total_criteria

    question_count = sum(1 for f in fields if f.get("type", 0) != 0)
    return question_count
