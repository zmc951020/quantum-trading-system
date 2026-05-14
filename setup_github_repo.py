#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub仓库创建和推送脚本
帮助用户在GitHub上创建仓库并推送代码
"""

import os
import sys
import requests
import base64
from github import Github

def create_github_repo(token, repo_name, repo_description, is_private=True):
    """
    创建GitHub仓库

    Args:
        token: GitHub Personal Access Token
        repo_name: 仓库名称
        repo_description: 仓库描述
        is_private: 是否私有

    Returns:
        仓库URL
    """
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "name": repo_name,
        "description": repo_description,
        "private": is_private,
        "auto_init": False
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        repo_url = response.json()["html_url"]
        print(f"仓库创建成功: {repo_url}")
        return repo_url
    elif response.status_code == 422:
        print("仓库已存在，将使用现有仓库")
        return f"https://github.com/{os.environ.get('GITHUB_USERNAME', 'user')}/{repo_name}"
    else:
        print(f"仓库创建失败: {response.status_code}")
        print(response.json())
        return None


def add_remote_and_push(repo_url):
    """
    添加远程仓库并推送代码

    Args:
        repo_url: 仓库URL
    """
    repo_name = repo_url.split("/")[-1].replace(".git", "")

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    os.system("git remote -v")

    os.system(f"git remote add origin {repo_url}.git")

    os.system("git branch -M main")

    print("\n请执行以下命令推送代码：")
    print(f"git push -u origin main")


def main():
    print("=" * 60)
    print("  GitHub仓库创建向导")
    print("=" * 60)

    print("\n请按照以下步骤操作：")
    print("-" * 60)
    print("1. 访问 https://github.com/settings/tokens")
    print("2. 创建新的Personal Access Token (Classic)")
    print("3. 勾选 'repo' 权限")
    print("4. 复制Token并粘贴到这里")
    print("-" * 60)

    token = input("\n请输入GitHub Token: ").strip()

    if not token:
        print("Token不能为空")
        return

    repo_name = "quantum-trading-system"
    repo_description = "量化交易系统 - 包含汇金价值AI轮动策略和Aurora交易平台"

    print(f"\n正在创建仓库: {repo_name}")
    repo_url = create_github_repo(token, repo_name, repo_description, is_private=False)

    if repo_url:
        print(f"\n仓库创建成功！")
        print(f"仓库地址: {repo_url}")
        print("\n下一步：")
        print("1. 访问仓库页面")
        print("2. 按照页面上的说明初始化仓库")
        print("   - 如果已有代码，选择 'push an existing repository'")
        print("   - 运行显示的命令")
        print(f"   - git remote add origin {repo_url}.git")
        print(f"   - git push -u origin main")


if __name__ == "__main__":
    main()