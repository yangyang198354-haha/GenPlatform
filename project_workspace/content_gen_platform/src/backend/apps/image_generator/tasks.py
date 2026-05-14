"""
图片生成 Celery 任务——豆包 Seedream Ark 版本。

改造要点（对比旧即梦版本）：
- 无轮询循环：Ark 为同步接口，单次 HTTP 调用直接返回图片 URL（ADR-03）
- 认证：Bearer Token（从 settings_vault 读取，service_type="doubao_image"）
- 批次模式：任务接收 batch_id，更新 ImageBatch 状态和 completed_count（ADR-04）
- 错误分类：DoubaoContentFilterError / DoubaoQuotaExceededError / DoubaoAuthError（ADR-07）

日志规范（NFR-4）：
- 记录：model、batch_id、task_id、耗时、成功/失败原因
- 禁止记录 API Key 任何形式（由 Logger filter 在 settings 层保证，此处不传 key 给 logger）

关联需求：FR-2、FR-3、FR-4、FR-5、ADR-03、ADR-07
"""
import base64
import logging
import os
import time

from celery import shared_task
from django.db import transaction
from django.db.models import F

from core.encryption import decrypt
from apps.settings_vault.models import UserServiceConfig
from apps.notifications.service import push_notification_sync
from apps.media_library.service import create_media_item_from_url
from .models import ImageBatch, ImageGenerationRequest
from .doubao_image_client import (
    DoubaoImageClient,
    DoubaoContentFilterError,
    DoubaoQuotaExceededError,
    DoubaoAuthError,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def generate_image_task(
    self,
    batch_id: int,
    advanced_params: dict | None = None,
    size: str = "2048x2048",
) -> None:
    """
    豆包 Ark 图片批次生成流水线。

    参数：
        batch_id: ImageBatch 的主键
        advanced_params: 高级生成参数字典（seed/guidance_scale 等，由 View 层传入）
        size: 图片尺寸（默认 "2048x2048"）

    任务流程：
    1. 从 DB 加载 ImageBatch 及关联的 ImageGenerationRequest（n 条）
    2. 从 settings_vault 读取解密后的 doubao_image API Key
    3. 若为图生图，读取临时文件并 base64 编码
    4. 调用 DoubaoImageClient.generate_images()（内部含 tenacity 重试）
    5. 清理临时参考图（try/finally，无论成功失败均执行，满足 AC-02-5）
    6. 逐张下载入库（create_media_item_from_url，provider="doubao"）
    7. 更新各 ImageGenerationRequest 的状态
    8. 原子更新 ImageBatch.completed_count（F() 表达式，避免竞态）
    9. 判断并更新 ImageBatch.status（completed / partial_failed / failed）
    10. WebSocket 推送 image_completed × n + batch_completed × 1

    参数：
        batch_id: ImageBatch 的主键

    错误分类处理（ADR-07）：
        DoubaoContentFilterError → failed，"提示词包含不允许的内容，请修改后重试"
        DoubaoQuotaExceededError → failed，"豆包 API 配额已耗尽，请检查账户余额"
        DoubaoAuthError          → failed，"豆包 API Key 无效，请重新配置"
        网络类错误（tenacity 耗尽后）→ failed，"网络连接失败，请稍后重试"
        其他 RuntimeError         → failed，记录完整 error_message
    """
    start_time = time.time()
    ref_image_path = None  # 用于 finally 块清理

    try:
        # ── Step 1: 加载批次及关联请求 ──────────────────────────────────────
        try:
            batch = ImageBatch.objects.select_related("user").get(pk=batch_id)
        except ImageBatch.DoesNotExist:
            logger.error("generate_image_task: ImageBatch #%d 不存在，任务终止", batch_id)
            return

        user = batch.user
        requests = list(batch.requests.order_by("id"))

        logger.info(
            "开始处理图片批次：batch_id=%d model=%s n=%d user=%s",
            batch_id, batch.model, batch.total_count, user.pk,
        )

        # ── Step 2: 获取 doubao_image API Key ───────────────────────────────
        try:
            doubao_cfg = UserServiceConfig.objects.get(
                user_id=user.pk, service_type="doubao_image", is_active=True
            )
            config = decrypt(bytes(doubao_cfg.encrypted_config))
            api_key = config["api_key"]
        except UserServiceConfig.DoesNotExist:
            _fail_batch(
                batch=batch,
                requests=requests,
                error_message="请先在设置中配置豆包 Ark API Key",
            )
            push_notification_sync(
                user.pk, "image_failed",
                {"batch_id": batch_id, "error": "请先在设置中配置豆包 Ark API Key"},
            )
            return

        # ── 更新批次状态为"处理中" ────────────────────────────────────────────
        batch.status = "processing"
        batch.save(update_fields=["status"])
        push_notification_sync(
            user.pk, "batch_progress",
            {"batch_id": batch_id, "status": "processing"},
        )

        # ── Step 3: 图生图——读取临时文件并 base64 编码 ─────────────────────────
        ref_image_b64 = None
        if batch.is_img2img and requests:
            ref_image_path = requests[0].ref_image_path or None
            if ref_image_path and os.path.exists(ref_image_path):
                try:
                    with open(ref_image_path, "rb") as f:
                        raw = f.read()
                    # 根据扩展名判断 MIME 类型
                    mime = "image/png" if ref_image_path.lower().endswith(".png") else "image/jpeg"
                    ref_image_b64 = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
                except OSError as exc:
                    logger.warning("读取参考图文件失败 %s: %s", ref_image_path, exc)
            else:
                logger.warning("图生图参考图路径无效或不存在：%s", ref_image_path)

        # ── Step 5: 准备 DoubaoImageClient ──────────────────────────────────
        client = DoubaoImageClient(api_key=api_key)

    except Exception as exc:
        # 任务启动阶段的意外错误
        logger.exception("generate_image_task 启动阶段异常：batch_id=%d", batch_id)
        try:
            batch = ImageBatch.objects.get(pk=batch_id)
            _fail_batch(batch=batch, requests=list(batch.requests.all()), error_message=str(exc))
        except Exception:
            pass
        return

    # ── 参考图清理（无论成功失败均执行，满足 AC-02-5）─────────────────────────
    try:
        _execute_generation(
            batch=batch,
            requests=requests,
            user=user,
            client=client,
            ref_image_b64=ref_image_b64,
            advanced_params=advanced_params or {},
            size=size,
            start_time=start_time,
        )
    finally:
        _cleanup_ref_image(ref_image_path)


def _execute_generation(
    batch: ImageBatch,
    requests: list,
    user,
    client: DoubaoImageClient,
    ref_image_b64,
    advanced_params: dict,
    size: str,
    start_time: float,
) -> None:
    """
    执行 Ark 调用、入库、推送通知、更新批次状态。

    此函数不处理参考图清理（由调用方的 finally 块负责）。
    """
    batch_id = batch.pk

    try:
        # ── 调用 Ark 接口（DoubaoImageClient 内部处理重试）─────────────────
        result = client.generate_images(
            prompt=batch.prompt,
            model=batch.model,
            n=batch.total_count,
            size=size,
            ref_image_b64=ref_image_b64,
            advanced_params=advanced_params,
        )
        image_urls = result.image_urls

        logger.info(
            "Ark 调用成功：batch_id=%d 耗时=%.1fs 返回 %d 张 URL",
            batch_id, time.time() - start_time, len(image_urls),
        )

    except DoubaoContentFilterError as exc:
        err_msg = "提示词包含不允许的内容，请修改后重试"
        logger.warning("内容审核拒绝：batch_id=%d", batch_id)
        _fail_batch(batch=batch, requests=requests, error_message=err_msg)
        push_notification_sync(user.pk, "image_failed", {"batch_id": batch_id, "error": err_msg})
        return

    except DoubaoQuotaExceededError as exc:
        err_msg = "豆包 API 配额已耗尽，请检查账户余额"
        logger.warning("配额耗尽：batch_id=%d", batch_id)
        _fail_batch(batch=batch, requests=requests, error_message=err_msg)
        push_notification_sync(user.pk, "image_failed", {"batch_id": batch_id, "error": err_msg})
        return

    except DoubaoAuthError as exc:
        err_msg = "豆包 API Key 无效，请重新配置"
        logger.warning("认证失败：batch_id=%d", batch_id)
        _fail_batch(batch=batch, requests=requests, error_message=err_msg)
        push_notification_sync(user.pk, "image_failed", {"batch_id": batch_id, "error": err_msg})
        return

    except Exception as exc:
        err_msg = str(exc) or "图片生成失败，请稍后重试"
        logger.exception("Ark 调用异常：batch_id=%d", batch_id)
        _fail_batch(batch=batch, requests=requests, error_message=err_msg)
        push_notification_sync(user.pk, "image_failed", {"batch_id": batch_id, "error": err_msg})
        return

    # ── 逐张入库并推送通知 ────────────────────────────────────────────────
    fail_count = 0
    for idx, url in enumerate(image_urls):
        # 找到对应 ImageGenerationRequest（按顺序匹配）
        req = requests[idx] if idx < len(requests) else None

        try:
            media_item = create_media_item_from_url(
                user=user,
                url=url,
                media_type="image",
                source="ai_generated",
                title=f"AI图片_{batch.prompt[:20]}",
                provider="doubao",
            )

            # 更新 ImageGenerationRequest 状态
            if req:
                req.status = "completed"
                req.result_image_url = url
                req.progress = 100
                req.media_item = media_item
                req.save(update_fields=["status", "result_image_url", "progress", "media_item"])

            # 原子递增 completed_count（F() 表达式，避免并发覆盖）
            with transaction.atomic():
                ImageBatch.objects.filter(pk=batch_id).update(
                    completed_count=F("completed_count") + 1
                )

            # 推送单张图片完成事件（AC-03-4）
            push_notification_sync(
                user.pk,
                "image_completed",
                {
                    "batch_id": batch_id,
                    "request_id": req.pk if req else None,
                    "media_item_id": media_item.pk,
                    "file_url": media_item.file.url,
                    "completed_count": idx + 1 - fail_count,
                    "total_count": batch.total_count,
                },
            )
            logger.info(
                "图片入库成功：batch_id=%d request_id=%s media_item_id=%d",
                batch_id, req.pk if req else "N/A", media_item.pk,
            )

        except Exception as exc:
            fail_count += 1
            err_msg = str(exc)
            logger.exception("图片入库失败：batch_id=%d url=%s", batch_id, url[:60])

            if req:
                req.status = "failed"
                req.error_message = err_msg
                req.save(update_fields=["status", "error_message"])

            push_notification_sync(
                user.pk,
                "image_failed",
                {
                    "batch_id": batch_id,
                    "request_id": req.pk if req else None,
                    "error": err_msg,
                },
            )

    # ── 更新批次最终状态 ───────────────────────────────────────────────────
    batch.refresh_from_db(fields=["completed_count"])
    success_count = batch.completed_count

    if success_count == batch.total_count:
        final_status = "completed"
    elif success_count > 0:
        final_status = "partial_failed"
    else:
        final_status = "failed"

    batch.status = final_status
    batch.save(update_fields=["status"])

    elapsed = time.time() - start_time
    logger.info(
        "批次生成完成：batch_id=%d status=%s 成功=%d/%d 耗时=%.1fs",
        batch_id, final_status, success_count, batch.total_count, elapsed,
    )

    push_notification_sync(
        user.pk,
        "batch_completed",
        {
            "batch_id": batch_id,
            "status": final_status,
            "completed_count": success_count,
            "total_count": batch.total_count,
        },
    )


def _fail_batch(
    batch: ImageBatch,
    requests: list,
    error_message: str,
) -> None:
    """将批次及所有关联请求置为失败状态。"""
    batch.status = "failed"
    batch.save(update_fields=["status"])

    for req in requests:
        req.status = "failed"
        req.error_message = error_message
        req.save(update_fields=["status", "error_message"])


def _cleanup_ref_image(ref_image_path) -> None:
    """
    清理临时参考图文件及其父目录（若为空）。
    满足 AC-02-5：任务结束后不留残留文件。
    """
    if not ref_image_path:
        return
    try:
        if os.path.exists(ref_image_path):
            os.remove(ref_image_path)
        parent = os.path.dirname(ref_image_path)
        if parent and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    except OSError as exc:
        logger.warning("清理参考图文件失败 %s: %s", ref_image_path, exc)
