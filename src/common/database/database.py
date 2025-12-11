from rich.traceback import install

from src.common.env_loader import load_project_env

install(extra_lines=3)

# 提前加载项目级环境变量，确保 maim_db 可以读取数据库配置
load_project_env()

try:
    from maim_db import get_database, init_database
except Exception as exc:
    raise RuntimeError(
        "maim_db 包未找到，请先通过 `pip install maim_db` 或 `pip install -e ../maim_db` 安装依赖"
    ) from exc

init_database()
db = get_database()
SAAS_MODE = True
