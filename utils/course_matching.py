"""Helpers for matching course rows across fresh queries and local cache.

The teaching-class operation token (``do_id``) is short lived and may change
every time the course list is queried.  A student's wishlist must therefore be
matched by the stable teaching-class identity instead.
"""

import re


def _text(value):
    """Return a normalized string suitable for an identity key."""
    return str(value or "").strip()


def normalize_manual_teacher(value):
    """Normalize teacher input against 正方's ``工号/姓名/职称`` format."""
    text = _text(value)
    parts = [part.strip() for part in text.split("/") if part.strip()]
    # Prefer the Chinese name segment returned by the teaching-class API.
    chinese = [part for part in parts if re.search(r"[\u4e00-\u9fff]", part)]
    return chinese[0] if chinese else text


def normalize_manual_time(value):
    """Ignore teaching-week suffixes such as ``{1-12周}`` when matching."""
    text = _text(value)
    text = re.sub(r"\s*\{[^{}]*\}\s*$", "", text)
    return re.sub(r"\s+", "", text)


def normalize_manual_weeks(value):
    """Normalize a week range such as ``1-12周`` or ``{1-12周}``."""
    text = _text(value).strip("{}")
    text = re.sub(r"\s+", "", text)
    return text.removesuffix("周")


def normalize_manual_course_code(value):
    """Normalize a course code entered by the user or returned by the API."""
    return re.sub(r"\s+", "", _text(value)).upper()


def course_weeks(value):
    """Extract the week suffix from the API's lesson-time text."""
    match = re.search(r"\{([^{}]+)\}\s*$", _text(value))
    return normalize_manual_weeks(match.group(1) if match else "")


def manual_course_matches(course, spec):
    """Match a manually entered course specification to an API row."""
    if not isinstance(course, dict) or not isinstance(spec, dict):
        return False
    title = _text(spec.get("title"))
    teacher = normalize_manual_teacher(spec.get("teacher"))
    course_code = normalize_manual_course_code(
        spec.get("course_code") or spec.get("course_id") or spec.get("kch_id")
    )
    weekday = _text(spec.get("weekday"))
    section = _text(spec.get("section"))
    if weekday and section:
        weekday_name = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "日"}.get(weekday, weekday)
        lesson_time = normalize_manual_time(f"星期{weekday_name}第{section}节")
    else:
        lesson_time = normalize_manual_time(spec.get("time"))
    lesson_weeks = normalize_manual_weeks(spec.get("weeks"))
    actual_title = _text(course.get("title"))
    actual_teacher = normalize_manual_teacher(course.get("teacher"))
    actual_course_code = normalize_manual_course_code(
        # 正方返回的 course_id/kch_id 可能是内部主键；用户在页面看到的
        # 课程代码通常位于 course_code/kch，优先使用可见课程代码匹配。
        course.get("course_code") or course.get("kch") or course.get("course_id") or course.get("kch_id")
    )
    actual_time = normalize_manual_time(course.get("time"))
    actual_weeks = course_weeks(course.get("time"))
    return (
        bool(title and teacher and lesson_time)
        and (not course_code or actual_course_code == course_code)
        and actual_title == title
        and (actual_teacher == teacher or teacher in actual_teacher or actual_teacher in teacher)
        and actual_time == lesson_time
        and (not lesson_weeks or actual_weeks == lesson_weeks)
    )


def course_identity(course):
    """Return a stable, hashable identity for a course/teaching class.

    ``class_id`` identifies a particular teaching class and is preferred over
    all other fields.  Older cache files may not have it, so a legacy fallback
    combines the stable course id with the visible section information.  The
    volatile ``do_id`` is intentionally never used.
    """
    if not isinstance(course, dict):
        return None

    class_id = _text(course.get("class_id"))
    if class_id:
        return ("class", class_id)

    return legacy_course_identity(course)


def legacy_course_identity(course):
    """Build the best identity available to old rows without ``class_id``."""
    if not isinstance(course, dict):
        return None
    course_id = _text(course.get("course_id"))
    title = _text(course.get("title"))
    teacher = _text(course.get("teacher"))
    time = _text(course.get("time"))
    if course_id:
        return ("course", course_id, title, teacher, time)
    if title or teacher or time:
        return ("legacy", title, teacher, time)
    return None


def remap_wishlist_courses(saved_courses, fresh_courses):
    """Replace wishlist rows with fresh rows while preserving order.

    A missing fresh row is retained as-is so a query cannot silently change or
    remove the student's chosen section.  Its stale token will be visible to
    the caller and can be refreshed on the next query.
    """
    fresh_by_identity = {}
    fresh_by_legacy_identity = {}
    for course in fresh_courses or []:
        identity = course_identity(course)
        if identity is not None:
            fresh_by_identity.setdefault(identity, course)
        legacy_identity = legacy_course_identity(course)
        if legacy_identity is not None:
            fresh_by_legacy_identity.setdefault(legacy_identity, []).append(course)

    remapped = []
    for saved in saved_courses or []:
        identity = course_identity(saved)
        if isinstance(saved, dict) and _text(saved.get("class_id")):
            fresh = fresh_by_identity.get(identity)
        else:
            candidates = fresh_by_legacy_identity.get(legacy_course_identity(saved), [])
            # Do not guess when multiple teaching classes have identical
            # visible fields; retaining the old row is safer than changing the
            # student's selected section.
            fresh = candidates[0] if len(candidates) == 1 else None
        remapped.append(fresh if fresh is not None else saved)
    return remapped
