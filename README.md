# agentes.chat 团队协作评测

在一台新电脑上运行同版本的 agentes.chat，自动创建一个“本地产品测评”工作区、三个真实可登录的账号，以及计划和物流各自的 Agent。启动使用官方 Linux 镜像，数据库使用 PostgreSQL 18 和 pgvector。

## 启动

准备 Linux/amd64 Docker Engine、Docker Compose v2 和 Python 3.11+。Windows 可用 Docker Desktop 的 Linux 容器模式，在有 Docker 集成的 WSL 中执行 Linux 命令也可以。首次在线启动需要能下载 GHCR、Docker Hub 的镜像。模型调用需要可用的 DeepSeek API Key 和出站网络。

解压 Release 源码包或克隆本仓库，打开该目录的终端。

**Windows**

优先双击 `Start.cmd`。它可以使用已有的 Python 3.11+，或从放在同一目录的官方便携 Python ZIP 准备本地运行环境。已有 Python 的电脑也可以在 PowerShell 执行：

```powershell
py -3 setup.py
```

**Linux 或 WSL**

```bash
python3 setup.py
```

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

默认仅绑定本机 `127.0.0.1`。在内网 Linux 服务器上验证时，可从客户端运行 `ssh -N -L 18813:127.0.0.1:18813 用户@服务器`，然后打开上述 localhost 网页。团队常态访问时可先在本机完成首次初始化，再在反向代理配置内网 HTTPS 域名，并把 `.env` 的 `PUBLIC_URL` 改为相同来源，执行 `docker compose up -d`。代理应转发全部页面、API 和 WebSocket 到同一应用。保留域名和端口的一致性。[上游自托管文档](https://github.com/agentes-chat/agentes-chat/blob/f409224e48dc374cc0709227e57807d18c3a11e9/SELF_HOSTING.md)

## 固定版本与离线启动

| 组件 | 采用的上游镜像 | linux/amd64 镜像配置 ID |
| --- | --- | --- |
| agentes.chat v0.1.7 | `ghcr.io/agentes-chat/agentes@sha256:b66c777d5aedf46571c9a52acdd7be2fd7cdc9dd8f9536cc6800a7a03897a610` | `sha256:f38dab1f5cf0dd07aeb367b21d1cc3ef5a1f6f49db8e3bce226ee835c8d111f5` |
| pgvector 0.8.7 / PostgreSQL 18 | `pgvector/pgvector:0.8.7-pg18@sha256:2358fcba361ed2233a5ed81b5fe4ca779ccb304120ce531a3bf51c0ed7e2bc11` | `sha256:55141572004e92a39edfdc2d16e821c214b64ca4fba50c1f7e408a09a3d04aff` |

agentes.chat 的源代码 revision 来自运行镜像 OCI 标签。[上游对应提交](https://github.com/agentes-chat/agentes-chat/tree/f409224e48dc374cc0709227e57807d18c3a11e9)

私有 Release 的离线镜像及校验步骤见 [OFFLINE.md](OFFLINE.md)。离线安装时先 `docker load -i 镜像归档.tar` 导入两张镜像，之后用 `python3 setup.py --offline` 或 `py -3 setup.py --offline`。也可在成功初始化的联网电脑上运行下面的命令自行制作镜像归档。它导出镜像，不含运行卷、账号数据或模型凭据。

```bash
docker image save -o agentes-images.tar agentes-evaluation/agentes:v0.1.7-f38dab1f5cf0 agentes-evaluation/pgvector:pg18-55141572004e
```

脚本逐个校验本地镜像的内容 ID，找不到匹配版本时，在线模式按固定摘要拉取。离线模式不拉取镜像。使用云端 DeepSeek 模型时，应用仍需访问提供商的 API。
