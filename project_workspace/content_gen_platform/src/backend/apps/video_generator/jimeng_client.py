"""Jimeng (即梦) API client for AI video generation."""
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import List

import httpx

logger = logging.getLogger(__name__)

JIMENG_API_BASE = "https://visual.volcengineapi.com"
JIMENG_SERVICE = "visual"
JIMENG_REGION = "cn-north-1"
JIMENG_VERSION = "2024-05-01"


@dataclass
class TaskStatus:
    task_id: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    progress: int  # 0-100
    clip_urls: List[str]
    error: str | None = None


class JimengAPIClient:
    """
    Volcengine Jimeng API client with HMAC-SHA256 request signing.
    Reference: https://www.volcengine.com/docs/6791/1389702
    """

    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key

    def _sign_request(self, method: str, path: str, params: dict, body: str) -> dict:
        """Generate Volcengine HMAC-SHA256 signature headers."""
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        date = timestamp[:8]

        canonical_query = "&".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )
        canonical_headers = f"content-type:application/json\nhost:{JIMENG_API_BASE.split('://')[1]}\nx-date:{timestamp}\n"
        signed_headers = "content-type;host;x-date"

        body_hash = hashlib.sha256(body.encode()).hexdigest()
        canonical_request = "\n".join([
            method,
            path,
            canonical_query,
            canonical_headers,
            signed_headers,
            body_hash,
        ])

        credential_scope = f"{date}/{JIMENG_REGION}/{JIMENG_SERVICE}/request"
        string_to_sign = "\n".join([
            "HMAC-SHA256",
            timestamp,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])

        def _hmac(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        signing_key = _hmac(
            _hmac(_hmac(_hmac(self.secret_key.encode(), date), JIMENG_REGION), JIMENG_SERVICE),
            "request",
        )
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

        return {
            "Content-Type": "application/json",
            "Host": JIMENG_API_BASE.split("://")[1],
            "X-Date": timestamp,
            "Authorization": (
                f"HMAC-SHA256 Credential={self.access_key}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }

    async def submit_task(self, scenes: list) -> str:
        """
        Submit a video generation task to Jimeng.
        Constructs a multi-shot prompt from scene list.
        Returns task_id.
        """
        # Build a combined prompt with scene descriptions
        scene_prompts = []
        for scene in scenes:
            prompt_part = (
                f"[Scene {scene['scene_index'] + 1}, {scene['duration_sec']}s, "
                f"transition:{scene['transition']}] {scene['scene_prompt']}"
            )
            scene_prompts.append(prompt_part)

        payload = {
            "req_key": "i2v_multi_scene",
            "scenes": [
                {
                    "prompt": s["scene_prompt"],
                    "narration": s["narration"],
                    "duration": s["duration_sec"],
                    "transition": s["transition"],
                }
                for s in scenes
            ],
        }

        body = json.dumps(payload)
        params = {"Action": "CVSubmitTask", "Version": JIMENG_VERSION}
        headers = self._sign_request("POST", "/", params, body)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                JIMENG_API_BASE,
                params=params,
                headers=headers,
                content=body,
            )
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("data", {}).get("task_id") or data.get("task_id")
            if not task_id:
                raise RuntimeError(f"Jimeng API 未返回 task_id: {data}")
            return task_id

    async def poll_status(self, task_id: str) -> TaskStatus:
        """Query the status of a submitted task."""
        params = {"Action": "CVQueryTask", "Version": JIMENG_VERSION}
        body = json.dumps({"task_id": task_id})
        headers = self._sign_request("POST", "/", params, body)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                JIMENG_API_BASE,
                params=params,
                headers=headers,
                content=body,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            raw_status = data.get("status", "pending")
            clip_urls = data.get("video_urls", [])
            progress = data.get("progress", 0)

            status_map = {
                "queue": "pending",
                "processing": "processing",
                "succeed": "completed",
                "failed": "failed",
            }
            return TaskStatus(
                task_id=task_id,
                status=status_map.get(raw_status, "pending"),
                progress=progress,
                clip_urls=clip_urls,
                error=data.get("error_message"),
            )
