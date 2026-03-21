# GitHub to GitLab & Codeberg Auto Sync (Mirror)

这是一个基于 GitHub Actions 和 Python 的自动化工具，用于将你名下所有的 GitHub 仓库（包括私有仓库）自动全量备份/同步到 **GitLab** 和/或 **Codeberg**。

它采用 `git clone --mirror` 和 `git push --mirror` 模式，确保**分支、标签、提交历史**与 GitHub 保持完全一致。

## ✨ 功能特点

*   **全自动化**：自动获取 GitHub 仓库列表，无需手动维护列表。
*   **自动创建**：如果目标平台上不存在对应仓库，会自动创建（默认私有）。
*   **全量镜像**：同步所有分支 (Branches) 和标签 (Tags)。
*   **定时运行**：默认每周一 UTC 20:00（北京时间周二凌晨 04:00）运行一次。
*   **支持强制推送**：GitHub 上的 `force push` 也会同步到目标平台，保证状态一致。
*   **私有仓库支持**：使用 Token 验证，支持私有仓库同步。
*   **多平台同步**：支持同时同步到 GitLab 和 Codeberg，也可按需只启用其中一个。

## 🚀 快速开始

### 1. 准备 Token

你需要获取各平台的访问令牌：

*   **GitHub Token (PAT)**（必填）:
    *   [Settings -> Developer settings -> Tokens (Classic)](https://github.com/settings/tokens)
    *   权限勾选: `repo` (全部), `read:user`。
*   **GitLab Token**（同步到 GitLab 时填写）:
    *   GitLab -> User Settings -> Access Tokens。
    *   权限勾选: `api`, `write_repository`。
*   **Codeberg Token**（同步到 Codeberg 时填写）:
    *   Codeberg -> User Settings -> Applications -> Manage Access Tokens。
    *   权限勾选: `issue`, `repository`（需包含写权限），以及 `user`（用于读取账号信息）。
    *   **注意**：如果你的 Token 没有 `user` 权限，也可以改为设置 `CB_USERNAME` Secret 来直接指定用户名（见下方配置表）。

### 2. 创建控制仓库

在 GitHub 上新建一个仓库（建议私有），例如命名为 `backup-center`。

### 3. 配置 Secrets

在仓库的 **Settings** -> **Secrets and variables** -> **Actions** 中添加以下 Repository secrets：

| Secret 名称 | 说明 | 示例值 | 是否必填 |
| :--- | :--- | :--- | :--- |
| `GH_PAT` | 你的 GitHub Personal Access Token | `ghp_xxxx...` | ✅ 必填 |
| `GL_TOKEN` | 你的 GitLab Access Token | `glpat-xxxx...` | 同步到 GitLab 时填写 |
| `GL_URL` | GitLab 的地址 | `https://gitlab.com` (或自建域名) | 同步到 GitLab 时填写 |
| `CB_TOKEN` | 你的 Codeberg Access Token | `xxxx...` | 同步到 Codeberg 时填写 |
| `CB_URL` | Codeberg 的地址 | `https://codeberg.org` (或自建域名) | 同步到 Codeberg 时填写（可选，有默认值） |
| `CB_USERNAME` | 你的 Codeberg 用户名 | `your-username` | 可选；若 Token 无 `user` 权限时必填 |

> **提示**：`GL_TOKEN` 和 `CB_TOKEN` 至少需要填写一个，也可以同时填写以实现双平台同步。

### 4. 添加代码文件

## ⚠️ 重要说明：关于强制推送 (Force Push)

本工具使用 `git push --mirror`，这意味着：

1.  **完全覆盖**：目标平台上的代码状态将被强制更新为 GitHub 的状态。
2.  **历史重写**：如果你在 GitHub 上使用了 `git push --force` 修改了提交历史，同步脚本也会**强制修改**目标平台上的历史。
3.  **删除操作**：如果你在 GitHub 上删除了某个分支，同步后目标平台上对应的分支也会被删除。

**如果遇到推送失败：**
如果在日志中看到"推送失败"，通常是因为目标平台的**分支保护 (Protected Branches)** 策略阻止了强制推送。
*   **GitLab 解决方法**：进入 GitLab 对应仓库 -> Settings -> Repository -> Protected branches -> 将 "Allowed to force push" 开启。
*   **Codeberg 解决方法**：进入 Codeberg 对应仓库 -> Settings -> Branches -> 移除或修改对应的保护规则。

## 📂 文件结构

```text
.
├── .github
│   └── workflows
│       └── sync.yml      # GitHub Actions 配置文件
├── README.md             # 说明文档
└── sync_tool.py          # 同步脚本核心逻辑
```
