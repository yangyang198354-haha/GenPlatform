"""Platform-specific publisher implementations."""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    success: bool
    post_id: str | None = None
    post_url: str | None = None
    error: str | None = None


class BasePlatformPublisher(ABC):
    @abstractmethod
    async def publish(self, title: str, body: str, credentials: dict) -> PublishResult:
        ...


class WeiboPublisher(BasePlatformPublisher):
    async def publish(self, title: str, body: str, credentials: dict) -> PublishResult:
        access_token = credentials.get("access_token", "")
        text = f"{title}\n\n{body}" if title else body
        text = text[:2000]  # Weibo character limit

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    "https://api.weibo.com/2/statuses/update.json",
                    data={"access_token": access_token, "status": text},
                )
                resp.raise_for_status()
                data = resp.json()
                return PublishResult(
                    success=True,
                    post_id=str(data.get("id")),
                    post_url=f"https://weibo.com/{data.get('user', {}).get('id')}/{data.get('mid', '')}",
                )
            except Exception as e:
                return PublishResult(success=False, error=str(e))


class XiaohongshuPublisher(BasePlatformPublisher):
    async def publish(self, title: str, body: str, credentials: dict) -> PublishResult:
        api_key = credentials.get("api_key", "")
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    "https://ark.cn-beijing.volces.com/xiaohongshu/v1/notes",  # placeholder
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"title": title, "content": body, "type": "normal"},
                )
                resp.raise_for_status()
                data = resp.json()
                return PublishResult(
                    success=True,
                    post_id=data.get("note_id"),
                    post_url=data.get("note_url"),
                )
            except Exception as e:
                return PublishResult(success=False, error=str(e))


class WechatMpPublisher(BasePlatformPublisher):
    async def publish(self, title: str, body: str, credentials: dict) -> PublishResult:
        access_token = credentials.get("access_token", "")
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # WeChat requires creating a draft first, then publishing
                draft_resp = await client.post(
                    f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}",
                    json={
                        "articles": [{"title": title, "content": body, "author": ""}]
                    },
                )
                draft_resp.raise_for_status()
                draft_data = draft_resp.json()
                media_id = draft_data.get("media_id")
                if not media_id:
                    return PublishResult(success=False, error=f"创建草稿失败: {draft_data}")

                publish_resp = await client.post(
                    f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={access_token}",
                    json={"media_id": media_id},
                )
                publish_resp.raise_for_status()
                return PublishResult(success=True, post_id=media_id)
            except Exception as e:
                return PublishResult(success=False, error=str(e))


class WechatVideoPublisher(BasePlatformPublisher):
    async def publish(self, title: str, body: str, credentials: dict) -> PublishResult:
        # WeChat Video (视频号) publishing requires video attachment;
        # for text-only posts we publish as a "feed" post
        access_token = credentials.get("access_token", "")
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    f"https://api.weixin.qq.com/cgi-bin/channels/ec/spu/get?access_token={access_token}",
                    json={"desc": body, "title": title},
                )
                resp.raise_for_status()
                data = resp.json()
                return PublishResult(success=True, post_id=data.get("spu_id"))
            except Exception as e:
                return PublishResult(success=False, error=str(e))


class ToutiaoPublisher(BasePlatformPublisher):
    async def publish(self, title: str, body: str, credentials: dict) -> PublishResult:
        access_token = credentials.get("access_token", "")
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    "https://open.mp.toutiao.com/api/content/article/publish/",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"title": title, "content": body, "article_type": 0},
                )
                resp.raise_for_status()
                data = resp.json()
                return PublishResult(
                    success=True,
                    post_id=str(data.get("article_id")),
                    post_url=data.get("article_url"),
                )
            except Exception as e:
                return PublishResult(success=False, error=str(e))


PUBLISHERS: dict[str, type[BasePlatformPublisher]] = {
    "weibo": WeiboPublisher,
    "xiaohongshu": XiaohongshuPublisher,
    "wechat_mp": WechatMpPublisher,
    "wechat_video": WechatVideoPublisher,
    "toutiao": ToutiaoPublisher,
}


def get_publisher(platform: str) -> BasePlatformPublisher:
    cls = PUBLISHERS.get(platform)
    if not cls:
        raise ValueError(f"Unknown platform: {platform}")
    return cls()
