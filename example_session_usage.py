#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SessionManager使用示例
展示如何使用新的Session管理功能
"""

from api.zfn_api import Client
import time

def main():
    # 配置
    base_url = "https://your-school.edu.cn"  # 替换为你的学校教务系统URL
    sid = "your_student_id"  # 替换为你的学号
    password = "your_password"  # 替换为你的密码
    
    print("=== SessionManager使用示例 ===")
    
    # 创建客户端
    client = Client(base_url=base_url)
    
    # 1. 登录
    print("\n1. 正在登录...")
    result = client.login(sid, password)
    if result['code'] == 1000:
        print("✅ 登录成功！")
    else:
        print(f"❌ 登录失败: {result['msg']}")
        return
    
    # 2. 查看登录状态
    print("\n2. 查看登录状态...")
    status = client.get_login_status()
    print(f"登录状态: {status}")
    
    # 3. 获取个人信息
    print("\n3. 获取个人信息...")
    info_result = client.get_info()
    if info_result['code'] == 1000:
        print("✅ 获取个人信息成功！")
        print(f"姓名: {info_result['data']['name']}")
        print(f"学号: {info_result['data']['sid']}")
        print(f"学院: {info_result['data']['college_name']}")
    else:
        print(f"❌ 获取个人信息失败: {info_result['msg']}")
    
    # 4. 测试Session持久性
    print("\n4. 测试Session持久性...")
    print("等待5秒后再次请求...")
    time.sleep(5)
    
    # 再次获取个人信息（应该自动维持登录状态）
    info_result2 = client.get_info()
    if info_result2['code'] == 1000:
        print("✅ Session持久性测试成功！自动维持了登录状态")
    else:
        print(f"❌ Session持久性测试失败: {info_result2['msg']}")
    
    # 5. 演示其他功能
    print("\n5. 演示其他功能...")
    
    # 获取当前学期成绩
    current_year = 2024
    current_term = 1
    
    grade_result = client.get_grade(current_year, current_term)
    if grade_result['code'] == 1000:
        print(f"✅ 获取成绩成功！共有 {grade_result['data']['count']} 门课程")
    else:
        print(f"❌ 获取成绩失败: {grade_result['msg']}")
    
    # 获取课程表
    schedule_result = client.get_schedule(current_year, current_term)
    if schedule_result['code'] == 1000:
        print(f"✅ 获取课程表成功！共有 {schedule_result['data']['count']} 门课程")
    else:
        print(f"❌ 获取课程表失败: {schedule_result['msg']}")
    
    print("\n=== 测试完成 ===")
    print("SessionManager自动维持了登录状态，无需手动管理Session！")

if __name__ == "__main__":
    main()