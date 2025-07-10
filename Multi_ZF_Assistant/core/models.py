from dataclasses import dataclass, field
from typing import List, Optional, Any
from datetime import datetime

@dataclass
class UserCredentials:
    """用户登录凭证"""
    url: str
    sid: str
    password: str

@dataclass
class Course:
    """课程基础信息模型"""
    course_id: Optional[str] = None
    title: Optional[str] = None
    teacher: Optional[str] = None
    class_name: Optional[str] = None
    credit: Optional[float] = None

@dataclass
class Grade(Course):
    """成绩信息模型"""
    category: Optional[str] = None
    nature: Optional[str] = None
    grade: Optional[str] = None
    grade_point: Optional[float] = None
    grade_nature: Optional[str] = None
    start_college: Optional[str] = None
    mark: Optional[str] = None

@dataclass
class Schedule(Course):
    """课表信息模型"""
    weekday: Optional[int] = None
    time: Optional[str] = None
    sessions: Optional[str] = None
    list_sessions: List[int] = field(default_factory=list)
    weeks: Optional[str] = None
    list_weeks: List[int] = field(default_factory=list)
    evaluation_mode: Optional[str] = None
    campus: Optional[str] = None
    place: Optional[str] = None
    hours_composition: Optional[str] = None
    weekly_hours: Optional[int] = None
    total_hours: Optional[int] = None

@dataclass
class Exam(Course):
    """考试安排模型"""
    time: Optional[str] = None
    location: Optional[str] = None
    xq: Optional[str] = None
    zwh: Optional[str] = None
    cxbj: Optional[str] = None
    exam_name: Optional[str] = None
    kkxy: Optional[str] = None
    ksfs: Optional[str] = None
    sjbh: Optional[str] = None
    bz: Optional[str] = None
    # 额外字段用于日历排序和显示
    sort_key: Optional[datetime] = None
    date_str: Optional[str] = None
    time_range: Optional[str] = None

@dataclass
class SelectableCourse(Course):
    """可选课程信息模型"""
    class_id: Optional[str] = None
    do_id: Optional[str] = None
    kklxdm: Optional[str] = None
    teacher_id: Optional[str] = None
    capacity: Optional[int] = None
    selected_number: Optional[int] = None
    category: Optional[str] = None
    optional: Optional[int] = None
    waiting: Optional[str] = None
    place: Optional[str] = None
    time: Optional[str] = None

@dataclass
class StudentInfo:
    """学生个人详细信息模型"""
    sid: Optional[str] = None
    name: Optional[str] = None
    college_name: Optional[str] = None
    major_name: Optional[str] = None
    class_name: Optional[str] = None
    status: Optional[str] = None
    enrollment_date: Optional[str] = None
    candidate_number: Optional[str] = None
    graduation_school: Optional[str] = None
    domicile: Optional[str] = None
    postal_code: Optional[str] = None
    politics_status: Optional[str] = None
    nationality: Optional[str] = None
    education: Optional[str] = None
    phone_number: Optional[str] = None
    parents_number: Optional[str] = None
    email: Optional[str] = None
    birthday: Optional[str] = None
    id_number: Optional[str] = None