# agentes.chat 团队协作评测

在一台新电脑上运行同版本的 agentes.chat，自动创建一个“本地产品测评”工作区、三个真实可登录的账号，以及计划和物流各自的 Agent。启动使用官方 Linux 镜像，数据库使用 PostgreSQL 18 和 pgvector。

## 启动

部署需要 Linux/amd64 容器、Docker Compose v2 和 Python 3.10 或更高版本。Ubuntu 22.04 可使用系统的 Python 3.10，初始化脚本只依赖 Python 标准库。Windows 使用 Docker Desktop 的 Linux 容器模式，WSL 可使用已集成的 Docker。首次在线启动需要能下载 GHCR、Docker Hub 的镜像。模型调用需要可用的 DeepSeek API Key 和出站网络。

解压 Release 源码包或克隆本仓库，打开该目录的终端。

**Windows**

优先双击 `Start.cmd`。它可以使用已有的 Python 3.10+，或从放在同一目录的官方便携 Python ZIP 准备本地运行环境。已有 Python 的电脑也可以在 PowerShell 执行：

```powershell
py -3 setup.py
```

**Ubuntu 22.04 / Linux / WSL**

在可读写的部署目录中操作，例如运维分配的项目目录。先确认当前账号能访问 Docker daemon，服务器架构应显示 `x86_64`。

```bash
uname -m
python3 --version
docker version --format '{{.Server.Version}}'
docker compose version
python3 setup.py
```

数据使用 Docker 命名卷，按该服务器已有的 Docker 数据目录存放。`docker info --format '{{.DockerRootDir}}'` 可查看实际位置。离线环境先按 [OFFLINE.md](OFFLINE.md) 校验和导入镜像，再执行 `python3 setup.py --offline`。

按提示输入一个至少 12 个字符的统一评测密码和共享 DeepSeek Key。计划员及物流员可分别输入自己的 Key，直接回车则沿用共享 Key。脚本通过应用的注册、邀请、接受邀请和密码登录接口创建账号，并逐一验证进入同一个频道。已有凭据和存储卷会复用。修复中断的首次初始化时，请输入原密码。

默认登录网页为 [http://localhost:18813/login](http://localhost:18813/login)。终端也会打印本工作区的频道直达网址。使用任一邮箱和自己刚选的密码。多角色并行测试时可使用不同浏览器配置文件，或一个普通窗口加一个无痕窗口。

| 账号 | 在工作区中的用途 |
| --- | --- |
| `admin@example.com` | “评测管理员”，新部署的工作区所有者，负责成员、模型和助手 |
| `planning@example.com` | 计划员，拥有 WMS 助手 `@wms` |
| `logistics@example.com` | 物流员，拥有双语助手 `@bilingual` |

## 验证协作

1. 用计划员登录，在 `#general` 发一条新消息「W-31 库位有两张标签待复核」，打开该消息的话题。
2. 用物流员打开同一话题，回复「两张标签均已复核」。两个账号都应看到这条回复。
3. 计划员在话题中输入 `@wms`，在提及列表中选择 **WMS 助手**，然后输入「请在本话题内公开提及双语助手，把以上交接情况交给它，请它直接在此回复英文摘要，保留库位和数量」。
4. 观察同一话题里的 Agent 回复和署名。可以在管理界面查看两位 Agent 的归属、模型和用量。后台不会因为初始化自动发送付费测评消息。

两位业务助手都使用 **DeepSeek V4.1 Flash**，对应本版提供商模型 ID `deepseek-flash`。工作区的模型路由、摘要、自动模型分档也设置为该模型。两个个人 Agent 各自绑定自己的模型凭据，未提供专用 Key 时使用同一共享凭据。需要更换 Key 时在管理员界面更新模型凭据及助手绑定。

## 常用操作

第一次换端口可运行 `python3 setup.py --port 18823`，Windows 使用 `py -3 setup.py --port 18823`。一个部署目录对应一套 `.env`。不要同时运行两个初始化进程。若已有同名 Compose 项目，启动前把 `COMPOSE_PROJECT_NAME` 设为新的项目名，并选择空闲端口。

```bash
docker compose ps
docker compose stop
docker compose up -d
docker compose logs --tail 80 agentes
```

初始化生成的 `.env` 内含此部署专用的数据库密码和凭据加密密钥。数据库保存在 `pgdata` 命名卷，上传文件保存在 `files` 卷。备份或迁移现有数据时需要同时保管这两个卷与该部署原来的 `.env`。初始登录密码由用户输入，模型 Key 通过应用接口保存。自动化环境可从秘密管理器注入 `EVAL_PASSWORD`、`DEEPSEEK_API_KEY`、`PLANNING_DEEPSEEK_API_KEY`、`LOGISTICS_DEEPSEEK_API_KEY`。这些变量用于初始化进程，不应写入仓库。

## 从办公电脑访问服务器

应用默认只监听服务器的 `127.0.0.1:18813`。首次初始化后，在服务器执行 `curl -fsS http://127.0.0.1:18813/api/health` 可检查应用就绪状态。

- **个人试用。** 如果 SSH 和堡垒机策略允许本地端口转发，在办公电脑执行 `ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18813:127.0.0.1:18813 用户@服务器`。保持终端开启，然后打开 [http://localhost:18813/login](http://localhost:18813/login)。若客户端的 18813 已被占用，可在首次部署选一个两端都空闲的端口（如 `--port 18823`），在命令和网址中同步替换端口。
- **团队共用或堡垒机禁用转发。** 先在服务器本机完成初始化，由运维将已批准的内网 HTTPS 域名代理到同机 `127.0.0.1:18813`。把 `.env` 的 `PUBLIC_URL` 改为该 HTTPS 来源（带非标准端口时需包含端口），再执行 `docker compose up -d`。所有人使用该域名的 `/login`。代理应保留 Host，转发页面、API 与 WebSocket 升级请求。[上游自托管文档](https://github.com/agentes-chat/agentes-chat/blob/f409224e48dc374cc0709227e57807d18c3a11e9/SELF_HOSTING.md)

## 固定版本与离线启动

| 组件 | 采用的上游镜像 | linux/amd64 镜像配置 ID |
| --- | --- | --- |
| agentes.chat v0.1.7 | `ghcr.io/agentes-chat/agentes@sha256:b66c777d5aedf46571c9a52acdd7be2fd7cdc9dd8f9536cc6800a7a03897a610` | `sha256:f38dab1f5cf0dd07aeb367b21d1cc3ef5a1f6f49db8e3bce226ee835c8d111f5` |
| pgvector 0.8.7 / PostgreSQL 18 | `pgvector/pgvector:0.8.7-pg18@sha256:2358fcba361ed2233a5ed81b5fe4ca779ccb304120ce531a3bf51c0ed7e2bc11` | `sha256:55141572004e92a39edfdc2d16e821c214b64ca4fba50c1f7e408a09a3d04aff` |

agentes.chat 的源代码 revision 来自运行镜像 OCI 标签。[上游对应提交](https://github.com/agentes-chat/agentes-chat/tree/f409224e48dc374cc0709227e57807d18c3a11e9)

私有 Release 的离线镜像及校验步骤见 [OFFLINE.md](OFFLINE.md)。将 Release 原包 `agentes-amd64.tar.gz` 放在脚本旁，用 `python3 setup.py --offline` 或 `Start.cmd --offline` 导入并启动。归档位于其他目录时追加 `--image-archive 文件路径`。也可在成功初始化的联网电脑上运行下面的命令自行制作镜像归档。它导出镜像，不含运行卷、账号数据或模型凭据。

```bash
docker image save -o agentes-images.tar agentes-evaluation/agentes:v0.1.7-f38dab1f5cf0 agentes-evaluation/pgvector:pg18-55141572004e
```

脚本按固定摘要核验镜像。经典存储读取配置 ID，Docker 29 的 containerd 存储读取与同一配置对应的 linux/amd64 manifest。在线模式缺镜像时从固定的源摘要拉取。离线模式不拉取镜像。使用云端 DeepSeek 模型时，应用仍需访问提供商的 API。
