import os
import time
import subprocess

import psycopg
from dotenv import load_dotenv

load_dotenv()


def ensure_postgres(container: str = "agent-postgres") -> None:
    """检查并自动启动 PostgreSQL Docker 容器。"""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        capture_output=True, text=True,
    )
 
    if result.stdout.strip() == "true":
        return  # 已在运行

    print(f"正在启动数据库容器 {container}...")
    subprocess.run(["docker", "start", container], capture_output=True)

    db_url = os.environ["DATABASE_URL"]
    for _ in range(15):
        try:
            psycopg.connect(db_url).close()
            print("数据库已就绪。")
            return
        except Exception:
            time.sleep(1)

    raise RuntimeError("数据库启动超时，请检查 Docker 是否正常运行。")
