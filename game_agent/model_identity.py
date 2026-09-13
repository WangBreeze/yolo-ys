"""Cheap local model revision stamp for cache invalidation; never contacts a hub."""

from importlib.metadata import version
from .contracts import fingerprint


def model_identity(context, options, package):
    path = context.input_path(options["model"])
    if not path.is_dir():
        raise FileNotFoundError(f"本地模型不存在：{path}；请运行 tools/fetch-video-models.py")
    files = [(str(p.relative_to(path)), p.stat().st_size, p.stat().st_mtime_ns)
             for p in sorted(path.rglob("*")) if p.is_file() and ".cache" not in p.parts]
    if not files:
        raise ValueError(f"empty local model: {path}")
    return {"model": str(path), "revision_stamp": fingerprint(files),
            "package": package, "package_version": version(package), "options": options}
