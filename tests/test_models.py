#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据模型
"""

import pytest
from core.models import UserCredentials, Course, Grade, Schedule, Exam


class TestUserCredentials:
    """测试用户凭证模型"""
    
    def test_user_credentials_creation(self):
        """测试用户凭证创建"""
        cred = UserCredentials(
            url="https://example.com",
            sid="123456",
            password="password"
        )
        
        assert cred.url == "https://example.com"
        assert cred.sid == "123456"
        assert cred.password == "password"


class TestCourse:
    """测试课程模型"""
    
    def test_course_creation(self):
        """测试课程创建"""
        course = Course(
            course_id="CS101",
            title="计算机科学导论",
            teacher="张教授",
            class_name="计科1班",
            credit=3.0
        )
        
        assert course.course_id == "CS101"
        assert course.title == "计算机科学导论"
        assert course.teacher == "张教授"
        assert course.class_name == "计科1班"
        assert course.credit == 3.0
    
    def test_course_default_values(self):
        """测试课程默认值"""
        course = Course()
        
        assert course.course_id is None
        assert course.title is None
        assert course.teacher is None
        assert course.class_name is None
        assert course.credit is None


class TestGrade:
    """测试成绩模型"""
    
    def test_grade_inheritance(self):
        """测试成绩模型继承"""
        grade = Grade(
            course_id="CS101",
            title="计算机科学导论",
            grade="85",
            grade_point=3.5
        )
        
        # 继承自Course的属性
        assert grade.course_id == "CS101"
        assert grade.title == "计算机科学导论"
        
        # Grade特有的属性
        assert grade.grade == "85"
        assert grade.grade_point == 3.5


class TestSchedule:
    """测试课表模型"""
    
    def test_schedule_with_lists(self):
        """测试包含列表的课表模型"""
        schedule = Schedule(
            course_id="CS101",
            title="计算机科学导论",
            weekday=1,
            list_sessions=[1, 2],
            list_weeks=[1, 2, 3, 4, 5]
        )
        
        assert schedule.weekday == 1
        assert schedule.list_sessions == [1, 2]
        assert schedule.list_weeks == [1, 2, 3, 4, 5]


class TestExam:
    """测试考试模型"""
    
    def test_exam_creation(self):
        """测试考试模型创建"""
        exam = Exam(
            course_id="CS101",
            title="计算机科学导论",
            time="2024-01-15 09:00-11:00",
            location="教学楼A101"
        )
        
        assert exam.course_id == "CS101"
        assert exam.title == "计算机科学导论"
        assert exam.time == "2024-01-15 09:00-11:00"
        assert exam.location == "教学楼A101"