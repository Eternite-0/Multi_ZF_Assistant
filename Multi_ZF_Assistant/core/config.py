# core/config.py

import configparser
import json
import os
from typing import Optional, Tuple, List
from .models import UserCredentials

CONFIG_FILE = 'config.ini'
ACCOUNTS_FILE = 'accounts.json'
WISHLISTS_FILE = 'wishlists.json'

def load_settings() -> int:
    """
    从 config.ini 文件加载设置。
    :return: 超时时间。
    """
    if not os.path.exists(CONFIG_FILE):
        return 10  # 默认值

    config = configparser.ConfigParser()
    try:
        config.read(CONFIG_FILE, encoding='utf-8')
        timeout = 10
        if 'Settings' in config:
            timeout = config['Settings'].getint('timeout', 10)
        return timeout
    except configparser.Error:
        return 10

def save_settings(timeout: int):
    """
    将设置保存到 config.ini 文件。
    :param timeout: 请求超时时间。
    """
    config = configparser.ConfigParser()
    config['Settings'] = {'timeout': str(timeout)}
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as cf:
            config.write(cf)
    except Exception as e:
        print(f"保存设置文件时出错: {e}")

def load_accounts() -> List[UserCredentials]:
    """
    从 accounts.json 文件加载所有账户凭证。
    :return: 一个包含 UserCredentials 对象的列表。
    """
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    
    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            accounts_data = json.load(f)
            return [UserCredentials(**data) for data in accounts_data]
    except (json.JSONDecodeError, TypeError) as e:
        print(f"读取账户文件时出错: {e}")
        return []

def save_accounts(accounts: List[UserCredentials]):
    """
    将账户列表保存到 accounts.json 文件。
    :param accounts: UserCredentials 对象列表。
    """
    try:
        accounts_data = [acc.__dict__ for acc in accounts]
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(accounts_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"保存账户文件时出错: {e}")

def load_wishlists() -> dict:
    """
    从 wishlists.json 文件加载所有账户的志愿列表。
    :return: 一个字典，键是学号(sid)，值是课程列表。
    """
    if not os.path.exists(WISHLISTS_FILE):
        return {}
    
    try:
        with open(WISHLISTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"读取志愿列表文件时出错: {e}")
        return {}

def save_wishlists(wishlists: dict):
    """
    将志愿列表字典保存到 wishlists.json 文件。
    :param wishlists: 包含各账户志愿的字典。
    """
    try:
        with open(WISHLISTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(wishlists, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"保存志愿列表文件时出错: {e}")