from pathlib import Path


def read_env_data_dir(project_root: Path) -> Path:
    """从 .env.prod 读取 data 配置项，返回绝对路径。"""
    env_file = project_root / ".env.prod"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "data":
                p = Path(value.strip())
                return p if p.is_absolute() else project_root / p
    return project_root / "data"
