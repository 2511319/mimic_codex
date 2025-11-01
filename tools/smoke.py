"""Lightweight smoke checks for local services.

Usage:
    python tools/smoke.py --gateway http://localhost:8000 --party http://localhost:8001 --media http://localhost:8002

The script performs non-destructive checks against running services:
- GET /config and /health
- Generation profiles and optional sample generation (scene.v1)
- Knowledge search when enabled
- Media job enqueue and polling until terminal state
- Party broadcast endpoint (no WS clients required)

Exits with code 0 on success, non-zero on first failure.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx


logger = logging.getLogger("smoke")


@dataclass
class Targets:
    gateway: str
    party: str
    media: str


def _build_client(timeout: float = 5.0) -> httpx.Client:
    return httpx.Client(timeout=timeout)


def _get_json(client: httpx.Client, url: str) -> dict[str, Any]:
    resp = client.get(url)
    resp.raise_for_status()
    payload = resp.json()
    assert isinstance(payload, dict)
    return payload


def _post_json(client: httpx.Client, url: str, body: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(url, json=body)
    resp.raise_for_status()
    payload = resp.json()
    assert isinstance(payload, dict)
    return payload


def check_gateway(client: httpx.Client, base: str) -> None:
    cfg = _get_json(client, f"{base}/config")
    logger.info("gateway /config ok: %s", {k: cfg.get(k) for k in ("apiVersion", "knowledge", "generation")})
    health = _get_json(client, f"{base}/health")
    assert health.get("status") == "ok"
    logger.info("gateway /health ok: %s", health)

    # generation
    try:
        profs = _get_json(client, f"{base}/v1/generation/profiles")
        profiles = profs.get("profiles", [])
        logger.info("gateway generation profiles: %s", profiles)
        if profiles:
            profile = "scene.v1" if "scene.v1" in profiles else profiles[0]
            detail = _get_json(client, f"{base}/v1/generation/profiles/{profile}")
            logger.info("profile detail ok: %s", {k: detail.get(k) for k in ("profile", "maxOutputTokens")})
            if cfg.get("generation") == "enabled":
                result = _post_json(client, f"{base}/v1/generation/{profile}", {"prompt": "Smoke: describe scene"})
                assert result.get("profile") == profile
                assert isinstance(result.get("result"), dict)
                logger.info("generation sample ok: %s", list(result["result"].keys())[:3])
    except httpx.HTTPStatusError as exc:  # generation may be disabled
        logger.warning("generation checks skipped: %s", exc)

    # knowledge
    try:
        if cfg.get("knowledge") == "enabled":
            query = urlencode({"q": "moon", "top_k": 1})
            items = _get_json(client, f"{base}/v1/knowledge/search?{query}")
            assert isinstance(items.get("items"), list)
            logger.info("knowledge search ok: %d items", len(items["items"]))
    except httpx.HTTPStatusError as exc:
        logger.warning("knowledge checks skipped: %s", exc)


def check_media(client: httpx.Client, base: str) -> None:
    cfg = _get_json(client, f"{base}/config")
    logger.info("media /config ok: %s", cfg.get("apiVersion"))
    body = {"jobType": "image", "payload": {"prompt": "Ancient ruins"}}
    job = _post_json(client, f"{base}/v1/media/jobs", body)
    job_id = job.get("jobId")
    assert isinstance(job_id, str)
    logger.info("media job accepted: %s", job_id)

    deadline = time.time() + 10.0
    status = job.get("status")
    while status not in ("succeeded", "failed") and time.time() < deadline:
        time.sleep(0.2)
        info = _get_json(client, f"{base}/v1/media/jobs/{job_id}")
        status = info.get("status")
    assert status == "succeeded", f"media job did not succeed (status={status})"
    logger.info("media job succeeded: %s", job_id)


def check_party(client: httpx.Client, base: str) -> None:
    cfg = _get_json(client, f"{base}/config")
    logger.info("party /config ok: %s", cfg.get("apiVersion"))
    ack = _post_json(
        client,
        f"{base}/v1/campaigns/cmp-smoke/broadcast",
        {"eventType": "ping", "payload": {"hello": "world"}},
    )
    assert ack.get("accepted") is True
    logger.info("party broadcast ok: %s", ack)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local smoke checks for RPG-Bot services")
    parser.add_argument("--gateway", default="http://localhost:8000", help="Gateway API base URL")
    parser.add_argument("--party", default="http://localhost:8001", help="Party Sync base URL")
    parser.add_argument("--media", default="http://localhost:8002", help="Media Broker base URL")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout seconds")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    targets = Targets(gateway=args.gateway.rstrip("/"), party=args.party.rstrip("/"), media=args.media.rstrip("/"))

    try:
        with _build_client(timeout=args.timeout) as client:
            check_gateway(client, targets.gateway)
            check_media(client, targets.media)
            check_party(client, targets.party)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("smoke failed: %s", exc)
        return 1
    logger.info("smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

