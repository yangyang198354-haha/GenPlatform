"""Jimeng (即梦) API client for AI image generation via CVProcess action."""
import base64
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from core.volcengine_signing import (
    JIMENG_API_BASE,
    JIMENG_VERSION,
    sign_request,
)

logger = logging.getLogger(__name__)


@dataclass
class ImageTaskStatus:
    task_id: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    progress: int  # 0-100
    image_urls: List[str] = field(default_factory=list)
    error: Optional[str] = None


class JimengImageClient:
    """
    Client for Jimeng (即创) image generation API.
    Uses CVProcess action with req_key for text-to-image and image-to-image.
    """

    # req_key for text-to-image generation (Jimeng CVProcess)
    IMG2IMG_REQ_KEY = "img_generation"

    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key

    def _make_headers(self, params: dict, body: str) -> dict:
        return sign_request(
            access_key=self.access_key,
            secret_key=self.secret_key,
            method="POST",
            path="/",
            params=params,
            body=body,
        )

    async def submit_image_task(
        self,
        prompt: str,
        ref_image_path: Optional[str] = None,
        width: int = 1024,
        height: int = 1024,
    ) -> str:
        """
        Submit an image generation task to Jimeng CVProcess.

        Args:
            prompt: Text description of the image to generate.
            ref_image_path: Optional local file path of a reference image.
            width: Output image width in pixels (default 1024).
            height: Output image height in pixels (default 1024).

        Returns:
            task_id string from Jimeng API.

        Raises:
            RuntimeError: if API call fails or no task_id returned.
        """
        payload: dict = {
            "req_key": self.IMG2IMG_REQ_KEY,
            "prompt": prompt,
            "width": width,
            "height": height,
            "return_url": True,
        }

        if ref_image_path:
            try:
                with open(ref_image_path, "rb") as f:
                    img_bytes = f.read()
                payload["binary_data_base64"] = [base64.b64encode(img_bytes).decode()]
            except OSError as exc:
                logger.warning("Could not read reference image %s: %s", ref_image_path, exc)

        body = json.dumps(payload)
        params = {"Action": "CVProcess", "Version": JIMENG_VERSION}
        headers = self._make_headers(params, body)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                JIMENG_API_BASE,
                params=params,
                headers=headers,
                content=body,
            )
            resp.raise_for_status()
            data = resp.json()

        # CVProcess may return task_id directly (async) or image URLs (sync)
        task_id = (
            data.get("data", {}).get("task_id")
            or data.get("task_id")
        )
        if not task_id:
            # Some Jimeng endpoints return image synchronously
            image_urls = (
                data.get("data", {}).get("image_urls")
                or data.get("image_urls", [])
            )
            if image_urls:
                # Return a synthetic task_id that encodes the result
                return f"sync:{image_urls[0]}"
            raise RuntimeError(f"即梦 API 未返回 task_id: {data}")

        return task_id

    async def poll_image_status(self, task_id: str) -> ImageTaskStatus:
        """
        Query the status of an image generation task.

        Args:
            task_id: The task_id returned by submit_image_task.

        Returns:
            ImageTaskStatus dataclass.
        """
        # Handle synchronous results encoded in task_id
        if task_id.startswith("sync:"):
            image_url = task_id[5:]
            return ImageTaskStatus(
                task_id=task_id,
                status="completed",
                progress=100,
                image_urls=[image_url],
            )

        params = {"Action": "CVGetResult", "Version": JIMENG_VERSION}
        body = json.dumps({"task_id": task_id})
        headers = self._make_headers(params, body)

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
        image_urls = data.get("image_urls", []) or data.get("images", [])
        progress = data.get("progress", 0)

        status_map = {
            "queue": "pending",
            "processing": "processing",
            "succeed": "completed",
            "done": "completed",
            "failed": "failed",
        }
        mapped_status = status_map.get(raw_status, "pending")

        return ImageTaskStatus(
            task_id=task_id,
            status=mapped_status,
            progress=progress if mapped_status != "completed" else 100,
            image_urls=image_urls,
            error=data.get("error_message"),
        )
