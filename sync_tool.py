import requests
import os
import subprocess
import shutil
import sys

# 从环境变量获取配置
GH_TOKEN = os.getenv('GH_PAT')
GL_TOKEN = os.getenv('GL_TOKEN')
GL_BASE_URL = os.getenv('GL_URL', 'https://gitlab.com').rstrip('/')

# 配置
SYNC_FORKS = True # 是否同步 Fork 的仓库，默认为 False
TEMP_DIR = 'temp_git_mirror'

if not GH_TOKEN or not GL_TOKEN:
    print("错误: 缺少环境变量 GH_PAT 或 GL_TOKEN")
    sys.exit(1)

# Header 设置
gh_headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3+json'}
gl_headers = {'Private-Token': GL_TOKEN}

def run_command(cmd, cwd=None):
    """执行 Shell 命令并屏蔽敏感信息"""
    try:
        # 这里的 capture_output=True 会隐藏输出，如果想看详细日志可以去掉
        subprocess.check_call(cmd, shell=True, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def get_github_repos():
    """获取所有 GitHub 仓库 (处理分页)"""
    print("正在获取 GitHub 仓库列表...")
    repos = []
    page = 1
    while True:
        url = f'https://api.github.com/user/repos?type=all&per_page=100&page={page}'
        r = requests.get(url, headers=gh_headers)
        if r.status_code != 200:
            print(f"GitHub API 错误: {r.status_code} {r.text}")
            break
        data = r.json()
        if not data:
            break
        for repo in data:
            if not SYNC_FORKS and repo.get('fork'):
                continue
            repos.append(repo)
        page += 1
    print(f"共发现 {len(repos)} 个仓库待同步。")
    return repos

def get_gitlab_user_info():
    """获取 GitLab 当前用户信息"""
    r = requests.get(f'{GL_BASE_URL}/api/v4/user', headers=gl_headers)
    if r.status_code == 200:
        return r.json()
    print("无法获取 GitLab 用户信息，请检查 Token 或 URL")
    sys.exit(1)

def ensure_gitlab_project(name, description, gl_user):
    """确保 GitLab 仓库存在，不存在则创建"""
    # 1. 尝试直接创建
    create_url = f'{GL_BASE_URL}/api/v4/projects'
    data = {
        'name': name,
        'description': description or f"Mirror of GitHub repo {name}",
        'visibility': 'private' # 默认全部私有，安全第一
    }
    r = requests.post(create_url, headers=gl_headers, data=data)
    
    repo_url_with_auth = ""
    
    if r.status_code == 201:
        print(f"[GitLab] 创建仓库成功: {name}")
    elif r.status_code == 400 and 'has already been taken' in r.text:
        # 已存在，不做处理
        pass
    else:
        print(f"[GitLab] 创建/检查仓库警告: {r.text}")

    # 构造带 Token 的推送地址 (兼容 HTTP/HTTPS)
    # 格式: https://oauth2:TOKEN@gitlab.com/username/repo.git
    clean_url = GL_BASE_URL.replace('https://', '').replace('http://', '')
    repo_url_with_auth = f"https://oauth2:{GL_TOKEN}@{clean_url}/{gl_user['username']}/{name}.git"
    
    return repo_url_with_auth

def sync_repo(repo, gl_user):
    repo_name = repo['name']
    print(f"\n>>> 开始处理: {repo_name}")
    
    # 清理残余
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        
    # 1. 获取/创建 GitLab 目标地址
    gl_push_url = ensure_gitlab_project(repo_name, repo['description'], gl_user)
    
    # 2. 从 GitHub 克隆 (Mirror 模式)
    # 构造带 Token 的 GitHub 拉取地址
    gh_clone_url = repo['clone_url'].replace('https://', f'https://oauth2:{GH_TOKEN}@')
    
    print(f"    1. 正在从 GitHub 克隆...")
    if not run_command(f"git clone --mirror {gh_clone_url} {TEMP_DIR}"):
        print(f"    [错误] 克隆失败，跳过。")
        return

    # 3. 推送到 GitLab
    print(f"    2. 正在推送到 GitLab...")
    if run_command(f"git push --mirror {gl_push_url}", cwd=TEMP_DIR):
        print(f"    [成功] {repo_name} 同步完成。")
    else:
        print(f"    [错误] 推送失败。")

    # 清理
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

if __name__ == "__main__":
    gl_user = get_gitlab_user_info()
    print(f"GitLab 用户: {gl_user['username']}")
    
    repos = get_github_repos()
    
    for repo in repos:
        try:
            sync_repo(repo, gl_user)
        except Exception as e:
            print(f"处理 {repo['name']} 时发生未知错误: {e}")
