"""Async media job manager."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import json
from typing import Dict
from uuid import uuid4

from .config import Settings
from .models import MediaJobRecord, MediaJobRequest, MediaJobResponse

logger = logging.getLogger(__name__)


class MediaJobManager:
    """In-memory media job orchestrator with async workers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jobs: "OrderedDict[str, MediaJobRecord]" = OrderedDict()
        self._jobs_by_token: Dict[str, str] = {}
        self._jobs_by_hash: Dict[str, str] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._workers: list[asyncio.Task[None]] = []
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        """Start background workers."""

        if self._workers:
            return
        self._shutdown.clear()
        for _ in range(self._settings.worker_concurrency):
            task = asyncio.create_task(self._worker_loop(), name="media-job-worker")
            self._workers.append(task)
        logger.info("Media broker started %d workers", len(self._workers))

    async def stop(self) -> None:
        """Stop workers gracefully."""

        self._shutdown.set()
        while not self._queue.empty():
            # unblock workers waiting on queue
            self._queue.put_nowait(None)  # type: ignore[arg-type]
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._workers.clear()

    async def enqueue(self, request: MediaJobRequest) -> MediaJobRecord:
        """Enqueue new job or return existing one for idempotent token."""

        async with self._lock:
            if request.client_token:
                existing_id = self._jobs_by_token.get(request.client_token)
                if existing_id:
                    logger.debug("Returning existing job for token %s", request.client_token)
                    return self._jobs[existing_id]

            job_hash = _job_hash(request.job_type, request.payload)
            if job_hash:
                existing_id = self._jobs_by_hash.get(job_hash)
                if existing_id:
                    logger.debug("Cache hit for media hash %s", job_hash)
                    return self._jobs[existing_id]

            job_id = uuid4().hex
            record = MediaJobRecord(
                jobId=job_id,  # type: ignore[arg-type]
                jobType=request.job_type,
                payload=request.payload,
                status="queued",
                clientToken=request.client_token,
            )
            self._jobs[job_id] = record
            if request.client_token:
                self._jobs_by_token[request.client_token] = job_id
            if job_hash:
                self._jobs_by_hash[job_hash] = job_id
            self._trim_history_locked()

        await self._queue.put(job_id)
        return record

    async def get_job(self, job_id: str) -> MediaJobRecord:
        """Return job by identifier."""

        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise KeyError(f"Job {job_id} not found")
            return record

    async def _worker_loop(self) -> None:
        try:
            while not self._shutdown.is_set():
                job_id = await self._queue.get()
                if job_id is None:
                    continue
                await self._process_job(job_id)
                self._queue.task_done()
        except asyncio.CancelledError:
            logger.debug("Worker cancelled")
            raise

    async def _process_job(self, job_id: str) -> None:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            record.status = "processing"
            record.updated_at = _now()

        await asyncio.sleep(self._settings.processing_delay_ms / 1000)

        try:
            result = self._build_result(record)
            async with self._lock:
                record.status = "succeeded"
                record.result = result
                record.error = None
                record.updated_at = _now()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Processing failed for job %s", job_id)
            async with self._lock:
                record = self._jobs[job_id]
                record.status = "failed"
                record.error = str(exc)
                record.result = None
                record.updated_at = _now()

    def _build_result(self, record: MediaJobRecord) -> dict[str, str | int | float]:
        if record.job_type == "tts":
            text = record.payload.get("text", "")
            duration_ms = max(400, len(text) * 40)
            return {
                "audioUrl": f"https://cdn.rpg/audio/{record.job_id}.ogg",
                "durationMs": duration_ms,
                "voice": record.payload.get("voice", "default"),
            }
        if record.job_type == "stt":
            return {
                "transcript": record.payload.get("stubTranscript", ""),
                "confidence": 0.92,
            }
        if record.job_type == "image":
            style = record.payload.get("style", "concept")
            return {
                "cdnUrl": f"https://cdn.rpg/images/{record.job_id}.webp",
                "style": style,
                "width": record.payload.get("width", 1024),
                "height": record.payload.get("height", 1024),
            }
        if record.job_type == "avatar":
            return {
                "cdnUrl": f"https://cdn.rpg/avatars/{record.job_id}.png",
                "seed": record.payload.get("seed", 0),
            }
        raise ValueError(f"Unsupported job type {record.job_type}")

    def _trim_history_locked(self) -> None:
        if len(self._jobs) <= self._settings.job_history_limit:
            return
        for job_id, record in list(self._jobs.items()):
            if record.status in {"succeeded", "failed"}:
                self._jobs.pop(job_id, None)
                if record.client_token:
                    self._jobs_by_token.pop(record.client_token, None)
                _remove_hash_reference(self._jobs_by_hash, job_id)
                if len(self._jobs) <= self._settings.job_history_limit:
                    break

    async def as_response(self, job_id: str) -> MediaJobResponse:
        record = await self.get_job(job_id)
        return MediaJobResponse.from_record(record)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _job_hash(job_type: str, payload: dict[str, object]) -> str:
    if job_type == "tts":
        key = {
            "jobType": "tts",
            "text": payload.get("text", ""),
            "voice": payload.get("voice", "default"),
            "speed": payload.get("speed", 1.0),
            "model": payload.get("model", "default"),
        }
    elif job_type == "image":
        key = {
            "jobType": "image",
            "prompt": payload.get("prompt", ""),
            "style": payload.get("style", "concept"),
            "seed": payload.get("seed", 0),
            "width": payload.get("width", 1024),
            "height": payload.get("height", 1024),
            "model": payload.get("model", "default"),
            "postproc": payload.get("postproc", "none"),
        }
    else:
        return ""

    raw = json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _remove_hash_reference(index: Dict[str, str], job_id: str) -> None:
    for key, value in list(index.items()):
        if value == job_id:
            index.pop(key, None)
