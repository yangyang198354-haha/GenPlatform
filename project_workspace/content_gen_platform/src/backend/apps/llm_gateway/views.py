"""LLM gateway: ProvidersView (新增) + GenerateContentView (重构) SSE 流式端点。

变更历史：
- PR-1: Content.provider/model 字段、UserLLMPreference 模型
- PR-2: selectors.py (list_available_providers / resolve_default / validate_choice)
- PR-3 (本次):
  - 新增 ProvidersView (GET /api/v1/llm/providers/)
  - GenerateContentView 同时支持 GET (向后兼容) 和 POST (新)
  - GET/POST 共用 _handle()：provider/model 解析全部交给 selectors
  - 删除原 views.py:68-80 的 .filter(...startswith="llm_"...).first() 无序 BUG
  - SSE done 事件新增 used_provider / used_model
  - SSE 流结束后写入 UserLLMPreference（偏好持久化）
  - 结构化日志：provider / model / latency_ms / success / error_code
"""
import json
import logging
import time
import concurrent.futures

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from core.encryption import decrypt
from apps.settings_vault.models import UserServiceConfig
from .providers import get_provider
from .selectors import (
    list_available_providers,
    resolve_default,
    validate_choice,
    NoAvailableProviderError,
    InvalidChoiceError,
)

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


# ---------------------------------------------------------------------------
# ProvidersView  GET /api/v1/llm/providers/
# ---------------------------------------------------------------------------

class ProvidersView(APIView):
    """返回当前登录用户可用的 LLM provider + model 列表。

    - 需要登录（401 由 DRF 认证类自动处理）
    - 响应头强制 Cache-Control: no-store（每次实时取 DB 状态）
    - 任何内部异常记录结构化日志后返回 500（不暴露 stacktrace）
    """

    def get(self, request):
        try:
            payload = list_available_providers(request.user)
        except Exception:
            logger.exception(
                "list_available_providers failed",
                extra={"user_id": request.user.pk},
            )
            return Response(
                {"error": "获取 provider 列表失败，请稍后重试"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = Response(payload)
        response["Cache-Control"] = "no-store"
        return response


# ---------------------------------------------------------------------------
# GenerateContentView  GET|POST /api/v1/llm/generate/
# ---------------------------------------------------------------------------

class GenerateContentView(APIView):
    """SSE endpoint: stream LLM-generated content to the client.

    同时支持 GET（向后兼容旧前端）和 POST（新前端，携带 provider/model 参数）。
    两种方法均调用 _handle()，差异仅在参数来源（query_params vs request.data）。

    GET 保留至下一个 major 版本（v2）废弃，文档标注 @deprecated。
    """

    def perform_content_negotiation(self, request, force=False):
        # SSE responses are text/event-stream — skip DRF's Accept-header
        # negotiation so it never raises a 406 Not Acceptable.
        renderers = self.get_renderers()
        return (renderers[0], renderers[0].media_type)

    # ── 参数解析 ──────────────────────────────────────────────────────────────

    def _parse_params(self, request):
        """统一解析 GET query_params 和 POST body 参数。"""
        if request.method == "POST":
            source = request.data
            use_kb_raw = source.get("use_kb", True)
            # POST body 可能是 JSON bool，也可能是字符串
            if isinstance(use_kb_raw, bool):
                use_kb = use_kb_raw
            else:
                use_kb = str(use_kb_raw).lower() in ("true", "1")
        else:
            source = request.query_params
            use_kb = source.get("use_kb", "true").lower() == "true"

        return {
            "prompt": str(source.get("prompt", "")).strip(),
            "platform": source.get("platform", "general"),
            "style": source.get("style", "professional"),
            "word_limit": source.get("word_limit"),
            "use_kb": use_kb,
            "provider": source.get("provider") or None,
            "model": source.get("model") or None,
        }

    # ── HTTP 方法入口 ─────────────────────────────────────────────────────────

    def get(self, request):
        """@deprecated — 向后兼容旧前端，v2 废弃。"""
        return self._handle(request)

    def post(self, request):
        return self._handle(request)

    # ── 核心处理逻辑 ──────────────────────────────────────────────────────────

    def _handle(self, request):
        params = self._parse_params(request)

        # 1. 校验 prompt 非空
        if not params["prompt"]:
            return Response(
                {"error": "prompt 不能为空"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. 校验 provider/model 必须同时传或同时省略
        provider_param = params["provider"]
        model_param = params["model"]
        if bool(provider_param) != bool(model_param):
            return Response(
                {
                    "error": "provider 与 model 必须同时传或同时省略",
                    "error_code": "INVALID_PARAMS",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. 解析实际使用的 service_type + model_id
        try:
            if provider_param and model_param:
                # 用户显式传参 → 走校验路径
                validate_choice(request.user, provider_param, model_param)
                service_type = provider_param
                model_id = model_param
            else:
                # 无参数 → 走默认决策链（向后兼容 GET 旧行为）
                service_type, model_id = resolve_default(request.user)
        except NoAvailableProviderError:
            return Response(
                {
                    "error": "请先配置 DeepSeek 服务，或在下拉框选择其他已配置的模型",
                    "error_code": "NO_AVAILABLE_PROVIDER",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InvalidChoiceError as exc:
            return Response(
                {"error": exc.message, "error_code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. 加载 provider 配置（精确 service_type 查询，消除旧 .first() BUG）
        try:
            llm_cfg = (
                UserServiceConfig.objects.filter(
                    user=request.user,
                    service_type=service_type,
                    is_active=True,
                )
                .order_by("-updated_at")
                .first()
            )
            if llm_cfg is None:
                raise RuntimeError(f"UserServiceConfig for {service_type} not found after validation")
            config = decrypt(bytes(llm_cfg.encrypted_config))
            provider_instance = get_provider(service_type, config, model=model_id)
        except Exception as exc:
            logger.exception(
                "LLM provider init failed",
                extra={"provider": service_type, "model": model_id},
            )
            return Response(
                {"error": f"LLM 配置加载失败：{exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 5. KB 搜索（逻辑不变，保留超时保护）
        context_parts = []
        used_doc_ids = []
        if params["use_kb"] and "apps.knowledge_base" in settings.INSTALLED_APPS:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_kb_search, request.user.pk, params["prompt"], top_k=5)
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

        # 6. 构建 messages
        system_prompt = PLATFORM_SYSTEM_PROMPTS.get(params["platform"], PLATFORM_SYSTEM_PROMPTS["general"])
        style_prompt = STYLE_PROMPTS.get(params["style"], "")
        word_limit = params["word_limit"]
        word_instruction = f"字数控制在 {word_limit} 字以内。" if word_limit else ""

        if context_parts:
            context_block = "\n\n".join(f"参考资料{i+1}：\n{c}" for i, c in enumerate(context_parts))
            full_system = f"{system_prompt}\n\n{style_prompt}\n\n以下是相关背景知识，请在生成时参考：\n{context_block}"
        else:
            full_system = f"{system_prompt}\n\n{style_prompt}"

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": f"{params['prompt']}\n\n{word_instruction}".strip()},
        ]

        # 7. SSE 响应（传入 provider/model/user 供 generator 写审计偏好和结构化日志）
        response = StreamingHttpResponse(
            _sync_sse_generator(
                provider_instance,
                messages,
                used_doc_ids,
                service_type=service_type,
                model_id=model_id,
                user=request.user,
            ),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


# ---------------------------------------------------------------------------
# SSE 生成器（扩展：used_provider/used_model + 偏好写入 + 结构化日志）
# ---------------------------------------------------------------------------

def _sync_sse_generator(
    provider,
    messages,
    used_doc_ids,
    service_type=None,
    model_id=None,
    user=None,
):
    """Run async SSE in a thread-safe way.

    在 SSE 流正常结束时：
    - done 事件新增 used_provider / used_model（前端乐观更新偏好）
    - 写入 UserLLMPreference（后端持久化偏好，设计文档 §4.3）
    - 打结构化日志（provider / model / latency_ms / success / error_code）

    在流失败时：
    - done 事件含 error 字段（与原逻辑一致）
    - 不写偏好（生成未成功，设计文档 §2.2）
    - 打结构化错误日志
    """
    import asyncio

    t_start = time.monotonic()

    async def _run():
        try:
            async for token in provider.stream_chat(messages):
                yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
            # 正常结束
            yield "__DONE_OK__"
        except Exception as exc:
            # 流失败
            yield f"__DONE_ERR__{exc}"

    loop = asyncio.new_event_loop()
    success = False
    error_code = None

    try:
        gen = _run()
        while True:
            try:
                chunk = loop.run_until_complete(gen.__anext__())
                if chunk == "__DONE_OK__":
                    # 正常结束：写偏好，发 done 事件（含 used_provider/used_model）
                    _persist_preference(user, service_type, model_id)
                    done_payload = {
                        "done": True,
                        "used_doc_ids": used_doc_ids,
                        "used_provider": service_type,
                        "used_model": model_id,
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n"
                    success = True
                    break
                elif isinstance(chunk, str) and chunk.startswith("__DONE_ERR__"):
                    exc_msg = chunk[len("__DONE_ERR__"):]
                    logger.error("SSE stream error during LLM call: %s", exc_msg)
                    error_code = "UPSTREAM_ERROR"
                    yield f"data: {json.dumps({'done': True, 'error': str(exc_msg)})}\n\n"
                    break
                else:
                    yield chunk
            except StopAsyncIteration:
                break
            except Exception:
                logger.exception("Unexpected error in SSE generator loop")
                error_code = "INTERNAL_ERROR"
                yield f"data: {json.dumps({'done': True, 'error': '服务器内部错误，请稍后重试'})}\n\n"
                break
    finally:
        loop.close()
        # 结构化日志（design.md §4.5）
        latency_ms = round((time.monotonic() - t_start) * 1000)
        if success:
            logger.info(
                "llm_generate success",
                extra={
                    "provider": service_type,
                    "model": model_id,
                    "latency_ms": latency_ms,
                    "success": True,
                },
            )
        else:
            logger.error(
                "llm_generate error",
                extra={
                    "provider": service_type,
                    "model": model_id,
                    "latency_ms": latency_ms,
                    "success": False,
                    "error_code": error_code,
                },
            )


def _persist_preference(user, service_type, model_id):
    """生成成功后写入 UserLLMPreference。

    静默失败：偏好写入不是关键路径，失败只记录 warning，不影响 SSE 流结果。
    （design.md §6 最后一行：偏好丢失不影响当次生成）
    """
    if user is None or service_type is None or model_id is None:
        return
    try:
        from apps.llm_gateway.models import UserLLMPreference  # noqa: PLC0415
        UserLLMPreference.objects.update_or_create(
            user=user,
            defaults={"service_type": service_type, "model": model_id},
        )
    except Exception:
        logger.warning(
            "Failed to persist UserLLMPreference",
            extra={"user_id": getattr(user, "pk", None), "provider": service_type, "model": model_id},
            exc_info=True,
        )
