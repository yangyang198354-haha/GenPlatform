"""
新增 Content.provider 和 Content.model 审计字段。

记录生成本条内容时实际使用的 LLM provider 和 model，
旧数据保持 NULL，向后兼容。

约束：
  - 均为 nullable（零停机，ALTER TABLE ADD COLUMN）
  - 不加 db_index（审计场景低频查询）
  - ContentSerializer 不暴露这两个字段（前端列表不展示）

回滚：
    python manage.py migrate content 0001_initial

创建时间：2026-05-15
关联需求：PR-1（LLM 模型选择功能）
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="content",
            name="provider",
            field=models.CharField(
                blank=True,
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="content",
            name="model",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
            ),
        ),
    ]
