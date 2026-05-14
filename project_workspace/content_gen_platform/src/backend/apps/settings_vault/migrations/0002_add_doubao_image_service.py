"""
空迁移：记录 settings_vault.SERVICE_CHOICES 新增 doubao_image 枚举值的版本信息。

Django choices 约束在 Python 层维护，无需对应的 DB 列定义变更。
此迁移作为版本锚点，便于 migration 历史追溯（ADR-06）。

关联需求：NFR-3、US-07、ADR-06
创建时间：2026-05-13

回滚：
    回滚此迁移不会影响数据库结构（无 DB 操作）。
    若需清理，仅需在 Python 代码中移除 doubao_image 枚举值即可。
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("settings_vault", "0001_initial")]

    operations = []
