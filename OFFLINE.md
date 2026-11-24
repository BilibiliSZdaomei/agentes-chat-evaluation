# 离线安装所需的容器镜像

在可访问 GitHub 的电脑登录仓库账号，从[此版本的依赖下载页](https://github.com/BilibiliSZdaomei/agentes-chat-evaluation/releases/tag/runtime-linux-amd64-20261124)下载 `SHA256SUMS` 和全部镜像附件。把附件放在同一目录，另将仓库源码下载或克隆到公司电脑。

镜像适用于 Linux x86_64，也可在 Windows x64 的 Docker Desktop（Linux 容器）中使用。安装 Docker 和 Docker Compose v2 后，在镜像下载目录执行下面的命令，然后按仓库首页启动。DeepSeek 在线对话需要从部署机访问模型服务，并使用你自己的 API Key。

**Windows**

将解压的仓库文件、`agentes-amd64.tar.gz` 放入同一目录，打开 Docker Desktop 后双击 `Start.cmd`。如果只想先导入镜像，可在 PowerShell 运行：

```powershell
.\Start.cmd --import-only --image-archive .\agentes-amd64.tar.gz
```

**Linux / WSL**

将 `agentes-amd64.tar.gz` 放入 `setup.py` 所在目录，然后运行：

```bash
python3 setup.py --offline
```

归档与源码不在同一目录时，指定实际文件，例如 `python3 setup.py --offline --image-archive ../downloads/agentes-amd64.tar.gz`。也可先执行 `python3 setup.py --import-only --image-archive ../downloads/agentes-amd64.tar.gz`，再运行 `python3 setup.py --offline`。

原版离线包包含两张无标签镜像，但 OCI 顶层索引只列出应用镜像。Docker 29 使用 containerd 存储时，直接执行 `docker load` 可能只导入其中一张。上述入口会核对归档 SHA-256，补全导入流中的应用与数据库索引及项目标签，并检查两份 linux/amd64 镜像配置。原归档可保留作下次部署用。已按旧说明导入的电脑可直接重跑上述命令。

Windows 没有 Python 时，同页另有 Python Software Foundation 的官方便携包 `python-3.14.10-embed-amd64.zip`。把 ZIP 原样放到 `Start.cmd` 旁边；双击时启动器核对 SHA-256 后自动解压。此附件无需导入 Docker。

同页的 `agentes-v0.1.7-source.tar.gz` 是该版本上游的对应源代码，保留原 LICENSE 和 NOTICE。
