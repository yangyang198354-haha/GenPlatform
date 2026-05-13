"""
图片生成模块路由配置——豆包 Seedream 版本。

新增端点：
    GET    /api/v1/image/batches/        批次列表（分页）
    GET    /api/v1/image/batches/{id}/   批次详情
    PATCH  /api/v1/image/batches/{id}/   批次重命名
    DELETE /api/v1/image/batches/{id}/   批次删除

关联需求：FR-5、US-05
"""
from django.urls import path

from .views import (
    ImageBatchDetailView,
    ImageBatchListView,
    ImageGenerationListView,
    ImageGenerationStatusView,
    ImageGenerationSubmitView,
)

urlpatterns = [
    # 提交生成请求（改造，豆包版本）
    path("generate/", ImageGenerationSubmitView.as_view(), name="image-generate"),
    # 单个请求状态查询（降级轮询接口，保留）
    path("generate/<int:pk>/status/", ImageGenerationStatusView.as_view(), name="image-status"),
    # 生成历史（保留，兼容旧即梦历史数据）
    path("history/", ImageGenerationListView.as_view(), name="image-history"),
    # 批次管理（新增，FR-5，US-05）
    path("batches/", ImageBatchListView.as_view(), name="image-batch-list"),
    path("batches/<int:pk>/", ImageBatchDetailView.as_view(), name="image-batch-detail"),
]
