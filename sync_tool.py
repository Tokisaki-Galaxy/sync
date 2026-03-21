import requests
import os
import subprocess
import shutil
import sys

# 从环境变量获取配置
def _get_env(name, default=None):
    """读取环境变量并去除首尾空白，空值返回 None（或指定默认值）"""
    value = (os.getenv(name) or '').strip()
    return value if value else default

GH_TOKEN = _get_env('GH_PAT')
GL_TOKEN = _get_env('GL_TOKEN')
GL_BASE_URL = _get_env('GL_URL', 'https://gitlab.com').rstrip('/')
CB_TOKEN = _get_env('CB_TOKEN')
CB_BASE_URL = _get_env('CB_URL', 'https://codeberg.org').rstrip('/')
CB_USERNAME = _get_env('CB_USERNAME')

# 配置
SYNC_FORKS = True # 是否同步 Fork 的仓库，默认为 False
TEMP_DIR = 'temp_git_mirror'

if not GH_TOKEN:
    print("错误: 缺少环境变量 GH_PAT")
    sys.exit(1)

if not GL_TOKEN and not CB_TOKEN:
    print("错误: 至少需要设置 GL_TOKEN 或 CB_TOKEN 其中之一")
    sys.exit(1)

# Header 设置
# GitLab 使用 Private-Token 认证，Codeberg (Gitea) 使用 Authorization: token 认证
gh_headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3+json'}
gl_headers = {'Private-Token': GL_TOKEN} if GL_TOKEN else {}
cb_headers = {'Authorization': f'token {CB_TOKEN}'} if CB_TOKEN else {}

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
    print(f"无法获取 GitLab 用户信息 (HTTP {r.status_code})，请检查 Token 或 URL。")
    print(f"  响应: {r.text[:200]}")
    sys.exit(1)

def ensure_gitlab_project(name, description, gl_user):
    """确保 GitLab 仓库存在，不存在则创建"""
    # 1. 尝试直接创建
    create_url = f'{GL_BASE_URL}/api/v4/projects'
    mirror_desc = f"Mirror of GitHub repo {name}. " + (description or "")
    data = {
        'name': name,
        'description': mirror_desc.strip(),
        'visibility': 'private' # 默认全部私有，安全第一
    }
    r = requests.post(create_url, headers=gl_headers, data=data)

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
    return f"https://oauth2:{GL_TOKEN}@{clean_url}/{gl_user['username']}/{name}.git"

def get_codeberg_user_info():
    """获取 Codeberg 当前用户信息"""
    # 如果用户已通过 CB_USERNAME 环境变量提供用户名，则跳过 API 调用
    if CB_USERNAME:
        print(f"  (使用 CB_USERNAME 环境变量作为用户名，跳过 API 用户信息查询)")
        return {'login': CB_USERNAME}
    r = requests.get(f'{CB_BASE_URL}/api/v1/user', headers=cb_headers)
    if r.status_code == 200:
        return r.json()
    print(f"无法获取 Codeberg 用户信息 (HTTP {r.status_code})，请检查 Token 权限或 URL。")
    print(f"  提示: Token 需要包含 'user' 权限范围 (scope)，或设置 CB_USERNAME 环境变量直接指定用户名。")
    print(f"  响应: {r.text[:200]}")
    sys.exit(1)

def ensure_codeberg_repo(name, description, cb_user):
    """确保 Codeberg 仓库存在，不存在则创建"""
    create_url = f'{CB_BASE_URL}/api/v1/user/repos'
    mirror_desc = f"Mirror of GitHub repo {name}. " + (description or "")
    data = {
        'name': name,
        'description': mirror_desc.strip(),
        'private': True, # 默认全部私有，安全第一
        'auto_init': False
    }
    r = requests.post(create_url, headers=cb_headers, json=data)

    if r.status_code == 201:
        print(f"[Codeberg] 创建仓库成功: {name}")
    elif r.status_code == 409:
        # 已存在，不做处理
        pass
    else:
        print(f"[Codeberg] 创建/检查仓库警告: {r.text}")

    # 构造带 Token 的推送地址
    # 格式: https://username:TOKEN@codeberg.org/username/repo.git
    clean_url = CB_BASE_URL.replace('https://', '').replace('http://', '')
    return f"https://{cb_user['login']}:{CB_TOKEN}@{clean_url}/{cb_user['login']}/{name}.git"

def sync_repo(repo, gl_user, cb_user):
    repo_name = repo['name']
    print(f"\n>>> 开始处理: {repo_name}")

    # 清理残余
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

    # 构造带 Token 的 GitHub 拉取地址
    gh_clone_url = repo['clone_url'].replace('https://', f'https://oauth2:{GH_TOKEN}@')

    print(f"    1. 正在从 GitHub 克隆...")
    if not run_command(f"git clone --mirror {gh_clone_url} {TEMP_DIR}"):
        print(f"    [错误] 克隆失败，跳过。")
        return

    step = 2

    # 推送到 GitLab
    if GL_TOKEN:
        gl_push_url = ensure_gitlab_project(repo_name, repo['description'], gl_user)
        print(f"    {step}. 正在推送到 GitLab...")
        if run_command(f"git push --mirror {gl_push_url}", cwd=TEMP_DIR):
            print(f"    [GitLab] {repo_name} 同步成功。")
        else:
            print(f"    [GitLab] 推送失败。")
        step += 1

    # 推送到 Codeberg
    if CB_TOKEN:
        cb_push_url = ensure_codeberg_repo(repo_name, repo['description'], cb_user)
        print(f"    {step}. 正在推送到 Codeberg...")
        if run_command(f"git push --mirror {cb_push_url}", cwd=TEMP_DIR):
            print(f"    [Codeberg] {repo_name} 同步成功。")
        else:
            print(f"    [Codeberg] 推送失败。")

    # 清理
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

if __name__ == "__main__":
    gl_user = None
    cb_user = None

    if GL_TOKEN:
        gl_user = get_gitlab_user_info()
        print(f"GitLab 用户: {gl_user['username']}")

    if CB_TOKEN:
        cb_user = get_codeberg_user_info()
        print(f"Codeberg 用户: {cb_user['login']}")

    repos = get_github_repos()

    for repo in repos:
        try:
            sync_repo(repo, gl_user, cb_user)
        except Exception as e:
            print(f"处理 {repo['name']} 时发生未知错误: {e}")
