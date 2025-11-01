"""Единый dev-ланчер для бэкендов и webapp.

Запускает локально три FastAPI‑сервиса (gateway_api, party_sync, media_broker)
и Vite webapp, прокидывая корректные VITE_* переменные. Ориентирован на
Windows/macOS/Linux без Poetry — использует активный интерпретатор Python.

Пример:
  python tools/dev_run.py            # запустить всё
  python tools/dev_run.py --smoke    # после старта прогнать smoke-скрипт

Требования: установлен npm, зависимости webapp (npm ci), python deps
установлены (pip install -e .; psycopg[binary]).
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import logging


logger = logging.getLogger("devrun")


def read_dotenv(path: Path) -> Dict[str, str]:
    """Минимальный парсер .env (ключ=значение, без экспорта).

    Args:
        path: Путь к .env файлу.

    Returns:
        Словарь переменных окружения.
    """

    env: Dict[str, str] = {}
    if not path.exists():
        return env
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    except Exception as exc:  # noqa: BLE001 - намеренно глушим чтение .env
        logger.warning("Не удалось прочитать .env: %s", exc)
    return env


def build_base_env(repo_root: Path) -> Dict[str, str]:
    """Собирает окружение для процессов (PYTHONPATH и .env).

    Returns:
        Готовый env словарь (на базе текущего окружения).
    """

    env = dict(os.environ)
    src_paths = [
        repo_root / "services/gateway_api/src",
        repo_root / "services/party_sync/src",
        repo_root / "services/media_broker/src",
        repo_root / "packages/memory37/src",
        repo_root / "packages/genlayers/src",
        repo_root / "packages/rpg_contracts/src",
    ]
    sep = ";" if os.name == "nt" else ":"
    pythonpath = sep.join(str(p) for p in src_paths)
    env["PYTHONPATH"] = pythonpath + (sep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    # Подмешиваем .env при наличии
    env.update(read_dotenv(repo_root / ".env"))

    # Значения по умолчанию для демо (не критично в проде)
    env.setdefault("API_VERSION", "1.0.0")
    env.setdefault("JWT_TTL_SECONDS", "900")
    env.setdefault("GENERATION_PROFILES_PATH", "profiles.yaml")
    env.setdefault("GENERATION_SCHEMA_ROOT", "contracts/jsonschema")
    # Для демо поиска знаний — YAML сэмпл
    sample_yaml = repo_root / "data/knowledge/sample.yaml"
    if sample_yaml.exists():
        env.setdefault("KNOWLEDGE_SOURCE_PATH", str(sample_yaml))

    return env


def start_process(cmd: List[str], *, cwd: Path | None, env: Dict[str, str], name: str) -> subprocess.Popen:
    """Стартует подпроцесс с логгером имени.

    Возвращает Popen; stdout/stderr ведём в родительскую консоль.
    """

    logger.info("Запуск %s: %s", name, " ".join(cmd))
    try:
        return subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=env)
    except FileNotFoundError as exc:
        logger.error("Команда не найдена (%s): %s", name, exc)
        raise


def run(smoke: bool, open_browser: bool) -> int:
    repo = Path(__file__).resolve().parents[1]
    env = build_base_env(repo)

    # Порты
    gw_port = int(os.environ.get("GW_PORT", "8000"))
    party_port = int(os.environ.get("PARTY_PORT", "8001"))
    media_port = int(os.environ.get("MEDIA_PORT", "8002"))
    web_port = int(os.environ.get("WEB_PORT", "4173"))

    # VITE окружение для фронта
    web_env = dict(env)
    web_env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{gw_port}"
    web_env.setdefault("VITE_MEDIA_BASE_URL", f"http://127.0.0.1:{media_port}")
    web_env.setdefault("VITE_PARTY_WS_URL", f"ws://127.0.0.1:{party_port}")

    # Команды
    procs: List[Tuple[str, subprocess.Popen]] = []
    try:
        procs.append(
            (
                "gateway",
                start_process(
                    [sys.executable, "-m", "uvicorn", "rpg_gateway_api.app:create_app", "--factory", "--reload", "--port", str(gw_port)],
                    cwd=repo,
                    env=env,
                    name="gateway_api",
                ),
            )
        )
        procs.append(
            (
                "party",
                start_process(
                    [sys.executable, "-m", "uvicorn", "rpg_party_sync.app:create_app", "--factory", "--reload", "--port", str(party_port)],
                    cwd=repo,
                    env=env,
                    name="party_sync",
                ),
            )
        )
        procs.append(
            (
                "media",
                start_process(
                    [sys.executable, "-m", "uvicorn", "rpg_media_broker.app:create_app", "--factory", "--reload", "--port", str(media_port)],
                    cwd=repo,
                    env=env,
                    name="media_broker",
                ),
            )
        )

        # Webapp dev server
        web_cwd = repo / "apps/webapp"
        procs.append(
            (
                "webapp",
                start_process(
                    ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(web_port)],
                    cwd=web_cwd,
                    env=web_env,
                    name="webapp",
                ),
            )
        )

        # Дать сервисам подняться
        time.sleep(2.0)
        logger.info("Сервисы запущены: gateway=%s, party=%s, media=%s, web=%s", gw_port, party_port, media_port, web_port)
        logger.info("WebApp: http://127.0.0.1:%s/", web_port)

        if open_browser:
            try:
                import webbrowser

                webbrowser.open(f"http://127.0.0.1:{web_port}/")
            except Exception:  # noqa: BLE001
                pass

        if smoke:
            try:
                logger.info("Запуск smoke-проверок...")
                code = subprocess.call(
                    [
                        sys.executable,
                        "tools/smoke.py",
                        "--gateway",
                        f"http://127.0.0.1:{gw_port}",
                        "--party",
                        f"http://127.0.0.1:{party_port}",
                        "--media",
                        f"http://127.0.0.1:{media_port}",
                    ],
                    cwd=str(repo),
                    env=env,
                )
                if code != 0:
                    logger.error("Smoke проверки завершились с кодом %s", code)
            except FileNotFoundError:
                logger.warning("tools/smoke.py не найден — пропускаю smoke")

        # Ожидание Ctrl+C
        logger.info("Нажмите Ctrl+C для остановки...")
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Остановка процессов...")
    finally:
        for name, p in procs:
            try:
                if p.poll() is None:
                    if os.name == "nt":
                        p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                    p.terminate()
            except Exception:  # noqa: BLE001
                pass
        # Дать время корректно завершиться
        time.sleep(0.5)
        for _, p in procs:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:  # noqa: BLE001
                pass
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    parser = argparse.ArgumentParser(description="Dev launcher for RPG-Bot monorepo")
    parser.add_argument("--smoke", action="store_true", help="Запустить smoke-проверки после старта")
    parser.add_argument("--open", action="store_true", help="Открыть webapp в браузере")
    args = parser.parse_args()
    return run(smoke=args.smoke, open_browser=args.open)


if __name__ == "__main__":
    raise SystemExit(main())

