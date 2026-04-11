"""LLM gateway: SSE streaming endpoint for content generation."""
import json
import logging
import asyncio
import concurrent.futures

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from core.encryption import decrypt
from apps.settings_vault.models import UserServiceConfig
from .providers import get_provider

# How long (seconds) to wait for KB search before giving up and continuing
# without context.  KB search loads a ~400 MB embedding model on first call;
# if the model isn't warmed yet we skip context rather than hanging the whole
# request and triggering nginx's proxy_read_timeout (504).
_KB_SEARCH_TIMEOUT_SECONDS = 8


def _kb_search(user_id, query, top_k=3):
    """Lazy wrapper so knowledge_base isn't imported at module load time."""
    from apps.knowledge_base.services import search  # noqa: PLC0415
    return search(user_id, query, top_k)

logger = logging.getLogger(__name__)

PLATFORM_SYSTEM_PROMPTS = {
    "weibo": "你是一名微博内容创作专家。微博字数限制2000字，适合简洁、口语化、情绪化的表达，配合热点话题标签。",
    "xiaohongshu": "你是一名小红书种草达人。文案要有个人感、生活感，使用表情符号，适合分段短句，末尾可以加话题标签。",
    "wechat_mp": "你是一名微信公众号内容编辑。文章结构清晰，适合深度内容，可加粗标题，注重阅读体验。",
    "wechat_video": "你是一名视频号文案创作者。文案简短有力，配合视频节奏，突出钩子开头，引导用户观看完整视频。",
    "toutiao": "你是一名头条号内容创作者。标题吸引眼球，内容信息密度高，适合资讯、干货类内容。",
    "general": "你是一名专业内容创作者，请根据用户需求生成高质量文案。",
}

STYLE_PROMPTS = {
    "professional": "请使用专业、严谨的语言风格。",
    "casual": "请使用轻松、口语化的语言风格。",
    "humorous": "请使用幽默、风趣的语言风格，可以使用类比和玩笑。",
    "promotion": "请使用有感染力的种草/促销语言风格，突出产品优势，激发购买欲望。",
}


class GenerateContentView(APIView):
    """SSE endpoint: stream LLM-generated content to the client."""

    def perform_content_negotiation(self, request, force=False):
        # SSE responses are text/event-stream — skip DRF's Accept-header
        # negotiation so it never raises a 406 Not Acceptable.
        renderers = self.get_renderers()
        return (renderers[0], renderers[0].media_type)

    def get(self, request):
        prompt = request.query_params.get("prompt", "").strip()
        platform = request.query_params.get("platform", "general")
        style = request.query_params.get("style", "professional")
        word_limit = request.query_params.get("word_limit")
        use_kb = request.query_params.get("use_kb", "true").lower() == "true"

        if not prompt:
            return Response({"error": "prompt 不能为空"}, status=status.HTTP_400_BAD_REQUEST)

        # Get user's active LLM config
        try:
            llm_cfg = UserServiceConfig.objects.filter(
                user=request.user,
                service_type__startswith="llm_",
                is_active=True,
            ).first()
            if not llm_cfg:
                return Response(
                    {"error": "请先在设置页面配置 LLM API Key"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            config = decrypt(bytes(llm_cfg.encrypted_config))
            provider = get_provider(llm_cfg.service_type, config)
        except Exception as e:
            logger.exception("LLM provider init failed")
            return Response({"error": f"LLM 配置加载失败：{e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Build context from knowledge base
        # Use a hard timeout so that a slow first-load of the embedding model
        # (or any other KB issue) never blocks the whole SSE request.
        context_parts = []
        used_doc_ids = []
        if use_kb and "apps.knowledge_base" in settings.INSTALLED_APPS:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_kb_search, request.user.pk, prompt, top_k=5)
                    chunks = future.result(timeout=_KB_SEARCH_TIMEOUT_SECONDS)
                for chunk in chunks:
                    context_parts.append(chunk.content)
                    if chunk.document_id not in used_doc_ids:
                        used_doc_ids.append(chunk.document_id)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "KB search timed out after %ss (model still loading?), "
                    "continuing without context",
                    _KB_SEARCH_TIMEOUT_SECONDS,
                )
            except Exception:
                logger.warning("KB search failed, continuing without context", exc_info=True)

        # Build messages
        system_prompt = PLATFORM_SYSTEM_PROMPTS.get(platform, PLATFORM_SYSTEM_PROMPTS["general"])
        style_prompt = STYLE_PROMPTS.get(style, "")
        word_instruction = f"字数控制在 {word_limit} 字以内。" if word_limit else ""

        if context_parts:
            context_block = "\n\n".join(f"参考资料{i+1}：\n{c}" for i, c in enumerate(context_parts))
            full_system = f"{system_prompt}\n\n{style_prompt}\n\n以下是相关背景知识，请在生成时参考：\n{context_block}"
        else:
            full_system = f"{system_prompt}\n\n{style_prompt}"

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": f"{prompt}\n\n{word_instruction}".strip()},
        ]

        response = StreamingHttpResponse(
            _sync_sse_generator(provider, messages, used_doc_ids),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


def _sync_sse_generator(provider, messages, used_doc_ids):
    """Run async SSE in a thread-safe way."""
    import asyncio

    async def _run():
        try:
            async for token in provider.stream_chat(messages):
                yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
            yield f"data: {json.dumps({'done': True, 'used_doc_ids': used_doc_ids})}\n\n"
        except Exception as exc:
            logger.exception("SSE stream error during LLM call")
            yield f"data: {json.dumps({'done': True, 'error': str(exc)})}\n\n"

    loop = asyncio.new_event_loop()
    try:
        gen = _run()
        while True:
            try:
                chunk = loop.run_until_complete(gen.__anext__())
                yield chunk
            except StopAsyncIteration:
                break
            except Exception:
                logger.exception("Unexpected error in SSE generator loop")
                yield f"data: {json.dumps({'done': True, 'error': '服务器内部错误，请稍后重试'})}\n\n"
                break
    finally:
        loop.close()
