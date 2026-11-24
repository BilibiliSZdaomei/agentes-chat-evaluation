"""Verify the two pinned images and import the original, untagged Release archive."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from typing import NamedTuple


class Image(NamedTuple):
    source: str
    config: str
    registry_manifest: str
    archive_manifest: str
    tag: str


RELEASE_NAME = "agentes-amd64.tar.gz"
RELEASE_SHA256 = "3853c09ce601200d18137970442fc785e904b78bd3f967f15584291daa86716c"
IMAGES = (
    Image("ghcr.io/agentes-chat/agentes@sha256:b66c777d5aedf46571c9a52acdd7be2fd7cdc9dd8f9536cc6800a7a03897a610",
          "sha256:f38dab1f5cf0dd07aeb367b21d1cc3ef5a1f6f49db8e3bce226ee835c8d111f5",
          "sha256:1b7f7560b17eac4124c3403a1e7cd3900eaad1c69e9513b113ed07e7602079ad",
          "sha256:6f44ae14fd7e1e8d323562fede33a84e0f9a56f89f11dffc28e7fd8cb21950e0",
          "agentes-evaluation/agentes:v0.1.7-f38dab1f5cf0"),
    Image("pgvector/pgvector:0.8.7-pg18@sha256:2358fcba361ed2233a5ed81b5fe4ca779ccb304120ce531a3bf51c0ed7e2bc11",
          "sha256:55141572004e92a39edfdc2d16e821c214b64ca4fba50c1f7e408a09a3d04aff",
          "sha256:ad249f9fb9572979643a47694e59b9a8cdcdf6abc6accebf49bb80ad5f20ff9b",
          "sha256:a6a815570082e2fa21279f9370e248d9771141e8d9f68a7ef68b894c9d2c2e98",
          "agentes-evaluation/pgvector:pg18-55141572004e"),
)


def docker_id(ref, platform=False):
    options = ["--platform", "linux/amd64"] if platform else []
    cmd = ["docker", "image", "inspect", *options, "--format", "{{.Id}}", ref]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def local_ref(image):
    # Classic image store addresses the config directly. The containerd store addresses
    # a manifest/index; its amd64 child is pinned above to the same immutable config.
    if docker_id(image.config) == image.config:
        return image.config
    allowed = {image.config, image.registry_manifest, image.archive_manifest}
    for ref in (image.tag, image.source, image.archive_manifest, image.registry_manifest):
        if docker_id(ref, platform=True) in allowed:
            return ref
    return None


def write_json(tar, name, obj):
    data = json.dumps(obj, separators=(",", ":")).encode("utf8")
    member = tarfile.TarInfo(name)
    member.size = len(data)
    tar.addfile(member, io.BytesIO(data))


def blob_name(digest):
    return "blobs/sha256/" + digest.split(":", 1)[1]


def tagged_stream(source, output):
    # The published archive has two complete manifest blobs but its OCI index only
    # references the first one. Some engines follow that index instead of manifest.json.
    manifests = {blob_name(i.archive_manifest): i for i in IMAGES}
    configs = {blob_name(i.config): i for i in IMAGES}
    descriptors = []
    verified_configs = set()
    legacy = []
    with tarfile.open(fileobj=source, mode="r|gz", bufsize=1024 * 1024) as old, tarfile.open(
            fileobj=output, mode="w|", bufsize=1024 * 1024, copybufsize=256 * 1024) as new:
        for member in old:
            name = member.name.removeprefix("./")
            if name == "index.json":
                continue
            data = old.extractfile(member) if member.isfile() else None
            if name == "manifest.json":
                legacy = json.load(data)
                continue
            if name in manifests or name in configs:
                blob = data.read()
                if blob_name("sha256:" + hashlib.sha256(blob).hexdigest()) != name:
                    raise ValueError("镜像元数据摘要与版本锁不一致。")
                meta = json.loads(blob)
                if name in manifests:
                    image = manifests[name]
                    if meta["config"]["digest"] != image.config:
                        raise ValueError("归档中的 manifest 指向了不同的镜像配置。")
                    descriptors.append({
                        "mediaType": meta["mediaType"], "size": len(blob), "digest": image.archive_manifest,
                        "platform": {"os": "linux", "architecture": "amd64"},
                        "annotations": {"io.containerd.image.name": "docker.io/" + image.tag,
                                        "org.opencontainers.image.ref.name": image.tag},
                    })
                else:
                    if (meta["os"], meta["architecture"]) != ("linux", "amd64"):
                        raise ValueError("离线镜像平台不匹配。")
                    verified_configs.add(name)
                data = io.BytesIO(blob)
            new.addfile(member, data)

        if ({d["digest"] for d in descriptors} != {i.archive_manifest for i in IMAGES}
                or verified_configs != set(configs) or {e["Config"] for e in legacy} != set(configs)):
            raise ValueError("归档缺少必要的两个镜像或配置。")
        for entry in legacy:
            entry["RepoTags"] = [configs[entry["Config"]].tag]
        write_json(new, "manifest.json", legacy)
        write_json(new, "index.json", {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
                                       "manifests": descriptors})


def load_release(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
        if digest.hexdigest() != RELEASE_SHA256:
            raise ValueError("离线归档 SHA-256 不匹配。请使用本 Release 的 " + RELEASE_NAME)
        source.seek(0)
        print("正在导入已校验的应用和数据库镜像…", flush=True)
        with subprocess.Popen(["docker", "image", "load"], stdin=subprocess.PIPE) as proc:
            try:
                tagged_stream(source, proc.stdin)
                proc.stdin.close()
            except BaseException:
                proc.kill()
                raise
            if proc.wait():
                raise ValueError("Docker 导入失败，请查看上方的引擎输出。")


def prepare_images(offline, archive=None):
    references = [local_ref(image) for image in IMAGES]
    if not all(references) and archive is not None:
        load_release(archive)
        references = [local_ref(image) for image in IMAGES]
    for image, ref in zip(IMAGES, references):
        if ref is None:
            if offline:
                raise ValueError("离线镜像不完整。把 " + RELEASE_NAME + " 放到脚本旁或指定 --image-archive。")
            subprocess.run(["docker", "pull", "--platform", "linux/amd64", image.source], check=True)
            ref = local_ref(image)
            if ref is None:
                raise ValueError("拉取的 linux/amd64 镜像与版本锁不匹配：" + image.tag)
        if ref != image.tag:
            subprocess.run(["docker", "tag", ref, image.tag], check=True)
