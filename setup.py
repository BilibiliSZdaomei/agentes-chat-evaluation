"""Start the pinned Linux/amd64 images and prepare a local, three-person evaluation."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from http.cookiejar import CookieJar
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parent
ORG = "本地产品测评"
MODEL = "deepseek-flash"
IMAGES = [
    ("ghcr.io/agentes-chat/agentes@sha256:b66c777d5aedf46571c9a52acdd7be2fd7cdc9dd8f9536cc6800a7a03897a610",
     "sha256:f38dab1f5cf0dd07aeb367b21d1cc3ef5a1f6f49db8e3bce226ee835c8d111f5",
     "agentes-evaluation/agentes:v0.1.7-f38dab1f5cf0"),
    ("pgvector/pgvector:0.8.7-pg18@sha256:2358fcba361ed2233a5ed81b5fe4ca779ccb304120ce531a3bf51c0ed7e2bc11",
     "sha256:55141572004e92a39edfdc2d16e821c214b64ca4fba50c1f7e408a09a3d04aff",
     "agentes-evaluation/pgvector:pg18-55141572004e"),
]
PEOPLE = {"admin": "评测管理员", "planning": "计划员", "logistics": "物流员"}
AGENTS = [
    ("planning", "wms", "WMS 助手",
     "根据话题中的库位、数量及待办核对仓库异常。如需双语交接，在当前话题的公开回复中写出 @bilingual 并附上库位、数量、任务，请它直接回复。保留 @bilingual 的原样提及；不发私信，不另开频道或话题。"),
    ("logistics", "bilingual", "双语助手",
     "把仓库交接写成简明英文，保留库位、数量和待办。在频道话题被提及时，直接在当前话题输出英文摘要即可，不使用私信，不查外部文档。"),
]


def docker(*args, quiet=False, check=True):
    return subprocess.run(["docker", *args], cwd=ROOT, check=check,
                          stdout=subprocess.PIPE if quiet else None,
                          stderr=subprocess.PIPE if quiet else None, text=True)


def prepare_images(offline):
    for ref, identity, tag in IMAGES:
        def present():
            result = docker("image", "inspect", "--format", "{{.Id}}", identity, quiet=True, check=False)
            return result.returncode == 0 and result.stdout.strip() == identity
        if not present():
            if offline:
                raise ValueError("缺少指定版本的离线镜像，请先 docker load 或联网运行。")
            docker("pull", "--platform", "linux/amd64", ref)
            if not present():
                raise ValueError("镜像与评测的 linux/amd64 配置摘要不一致。")
        docker("tag", identity, tag)


def config(port):
    path = ROOT / ".env"
    if not path.exists():
        number = port or 18813
        body = (f"HOST_PORT={number}\nPUBLIC_URL=http://localhost:{number}\n"
                f"BIND_ADDRESS=127.0.0.1\nPOSTGRES_PASSWORD={secrets.token_hex(32)}\n"
                f"AGENTES_SECRET={secrets.token_hex(48)}\n")
        # Never overwrite the encryption secret of an existing database.
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf8") as out:
            out.write(body)
    values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8-sig").splitlines()
                  if line.strip() and not line.lstrip().startswith("#"))
    actual = int(values["HOST_PORT"])
    if port and actual != port:
        raise ValueError(".env 与 --port 不一致，请先核对这个部署目录。")
    return actual, values["PUBLIC_URL"].rstrip("/")


class APIError(Exception):
    def __init__(self, status, path, code):
        self.status = status
        # Invitation addresses contain a one-use proof. Never include them in output.
        safe_path = re.sub(r"/invitations/[^/]+/accept", "/invitations/[邀请]/accept", path)
        super().__init__(f"{safe_path} HTTP {status} {code}")


class Client:
    def __init__(self, url):
        self.url = url
        self.opener = request.build_opener(request.ProxyHandler({}), request.HTTPCookieProcessor(CookieJar()))

    def call(self, method, path, data=None, extra=None, retry_auth=True):
        headers = {"Origin": self.url, "Referer": self.url + "/", **(extra or {})}
        raw = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            raw = json.dumps(data, ensure_ascii=False).encode("utf8")
        req = request.Request(self.url + path, raw, headers, method=method)
        try:
            with self.opener.open(req, timeout=30) as response:
                body = response.read()
        except error.HTTPError as ex:
            if retry_auth and ex.code == 429 and path == "/api/auth/sign-in/email":
                wait = ex.headers.get("Retry-After", "")
                seconds = min(int(wait) + 1, 65) if wait.isdigit() else 62
                ex.close()
                print(f"应用限制了连续登录请求，{seconds} 秒后再验证。", flush=True)
                time.sleep(seconds)
                return self.call(method, path, data, extra, retry_auth=False)
            try:
                code = json.loads(ex.read()).get("code", "")
            except (ValueError, AttributeError):
                code = ""
            raise APIError(ex.code, path, code if isinstance(code,str) and re.fullmatch(r"[\w.-]{1,70}",code) else "") from None
        return json.loads(body) if body else {}


def authenticate(c, role, password, invitation=None):
    data = {"email": role + "@example.com", "password": password}
    try:
        c.call("POST", "/api/auth/sign-in/email", data)
    except APIError as e:
        if e.status not in (400, 401, 403): raise
        c.call("POST", "/api/auth/sign-up/email", {**data, "name": PEOPLE[role]},
               {"x-invitation-token": invitation} if invitation else {})
        c.call("POST", "/api/auth/sign-in/email", data)
    me = c.call("GET", "/api/app/me")
    if me["user"]["email"] != data["email"]:
        raise ValueError("账号身份与评测邮箱不一致。")
    return me


def ensure_org(c, me):
    organizations = me["organizations"]
    target = next((o for o in organizations if o["name"] == ORG), None)
    if target: return target["id"]
    if organizations:
        raise ValueError("管理员已属于其他工作区。请使用全新评测卷，或核对原工作区名称。")
    return c.call("POST", "/api/app/organizations", {
        "name": ORG, "context": "计划与物流核对仓库交接，人员和各自的 Agent 在同一频道协作。"
    })["organization"]["id"]


def ensure_people(c, org, password):
    members = c.call("GET", org + "/members")["members"]
    for role in ("planning", "logistics"):
        mail = role + "@example.com"
        member = next((m for m in members if m["email"] == mail), None)
        peer = Client(c.url)
        if member:
            authenticate(peer, role, password)
            continue
        invites = c.call("GET", org + "/invitations")["invitations"]
        pending = next((v for v in invites if v["email"] == mail), None)
        inv = (c.call("POST", org + "/invitations/" + pending["id"] + "/resend", {}) if pending else
               c.call("POST", org + "/invitations", {"email": mail}))
        token = parse.urlsplit(inv["url"]).path.rsplit("/", 1)[1]
        authenticate(peer, role, password, token)
        peer.call("POST", "/api/app/invitations/" + parse.quote(token, safe="") + "/accept", {})
    result = c.call("GET", org + "/members")["members"]
    return {m["email"].split("@")[0]: m["userId"] for m in result if m["email"] in {r+"@example.com" for r in PEOPLE}}


def model_credentials(c, org):
    current = c.call("GET", org + "/credentials")["credentials"]
    ids = {}
    for role, var, label in (("shared", "DEEPSEEK_API_KEY", "共享"),
                             ("planning", "PLANNING_DEEPSEEK_API_KEY", "计划"),
                             ("logistics", "LOGISTICS_DEEPSEEK_API_KEY", "物流")):
        name = "DeepSeek · " + label
        existing = next((v for v in current if v["provider"] == "deepseek" and
                         v["label"] == name and not v.get("revokedAt")), None)
        if existing:
            ids[role] = existing["id"]
            continue
        supplied = os.environ.get(var) or ""
        if not supplied and sys.stdin.isatty():
            supplied = getpass.getpass(label + (" DeepSeek API Key: " if role=="shared" else "专用 Key（回车沿用共享）: ")).strip()
        if not supplied and role != "shared":
            ids[role] = ids["shared"]
            continue
        if not supplied:
            raise ValueError("首次配置请提供 DEEPSEEK_API_KEY，或在终端按提示输入。")
        ids[role] = c.call("POST", org + "/credentials", {
            "provider":"deepseek", "label": name, "apiKey": supplied, "makeDefault": role == "shared"
        })["id"]
    c.call("PATCH", org + "/settings", {
        "defaultCredentialId": ids["shared"], "defaultCredentialIds":{"deepseek": ids["shared"]},
        "routerModel":MODEL, "summaryModel":MODEL,
        "autoModels":{"deepseek":{"small":MODEL,"medium":MODEL,"large":MODEL}}
    })
    return ids


def prepare_agents(c, org, channel, people, ids):
    agents = c.call("GET", org + "/agents")["agents"]
    membership = org + "/channels/" + channel + "/members"
    current = {m["id"] for m in c.call("GET", membership)["members"]}
    for role, handle, name, instructions in AGENTS:
        fields = {"name":name, "instructions":instructions, "model":MODEL, "credentialId":ids[role]}
        agent = next((a for a in agents if a["handle"] == handle), None)
        if not agent:
            agent = c.call("POST", org + "/agents", {"handle":handle, **fields})
        path = org + "/agents/" + agent["id"]
        c.call("PATCH", path, {**fields, "ownerUserId":people[role]})
        actual = c.call("GET", path)
        if any(actual[k] != value for k,value in (("model",MODEL),("credentialId",ids[role]),("ownerUserId",people[role]))):
            raise ValueError("Agent 归属或模型验证失败：" + handle)
        if agent["id"] not in current:
            c.call("POST", membership, {"agentId":agent["id"]})
    lodi = next((a for a in agents if a["handle"] == "lodi"), None)
    if lodi:
        c.call("PATCH", org + "/agents/" + lodi["id"], {"model":MODEL, "credentialId":ids["shared"]})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, help="首次启动使用的本机 HTTP 端口，默认 18813")
    ap.add_argument("--offline", action="store_true", help="仅使用已导入的匹配镜像")
    args = ap.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535: ap.error("端口超出范围")
    docker("compose","version",quiet=True)
    prepare_images(args.offline)
    port, url = config(args.port)
    if url not in (f"http://localhost:{port}", f"http://127.0.0.1:{port}"):
        raise ValueError("请使用原本机回环 PUBLIC_URL 初始化，再按 README 配置内网域名。")
    docker("compose","up","-d")
    c = Client(url)
    for _ in range(100):
        try:
            c.call("GET","/api/health")
            break
        except (OSError, APIError):
            time.sleep(2)
    else:
        raise ValueError("网页服务仍未就绪，请查看 docker compose logs --tail 80。")
    password = os.environ.get("EVAL_PASSWORD") or getpass.getpass("三个评测账号的统一密码（至少 12 个字符）: ")
    if len(password) < 12: raise ValueError("密码至少 12 个字符。")
    me = authenticate(c,"admin",password)
    oid = ensure_org(c,me)
    org = "/api/app/organizations/" + oid
    people = ensure_people(c,org,password)
    channel = next(ch["id"] for ch in c.call("GET",org+"/channels")["channels"] if ch["name"]=="general")
    ids = model_credentials(c, org)
    prepare_agents(c, org, channel, people, ids)
    for role in PEOPLE:
        peer = Client(url)
        session = authenticate(peer,role,password)
        if oid not in [o["id"] for o in session["organizations"]]:
            raise ValueError("成员的工作区验证失败：" + role)
        peer.call("GET",org + "/channels/" + channel + "/messages")
    print("3 个账号均能登录同一工作区。DeepSeek 默认模型：" + MODEL)
    print("浏览器登录页：" + url + "/login")
    print("协作频道：" + url + "/org/" + oid + "/c/" + channel)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, APIError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit("初始化未完成：" + str(exc))
