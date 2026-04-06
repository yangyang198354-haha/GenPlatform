<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-04-06T00:20:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>architecture/module_design.md (APPROVED)</file>
    <file>architecture/architecture_design.md (APPROVED)</file>
    <file>architecture/tech_stack.md (APPROVED)</file>
  </input_files>
  <phase>PHASE_05</phase>
  <status>APPROVED</status>
</file_header>

# 实现计划 — 内容生成平台

## 实现顺序（拓扑排序）

1. **MOD-008 settings_vault** — 无依赖，加密工具类最先实现
2. **MOD-001 accounts** — 依赖 settings_vault 的加密模块
3. **MOD-002 knowledge_base** — 依赖 accounts（用户隔离）
4. **MOD-003 llm_gateway** — 依赖 accounts + settings_vault
5. **MOD-004 content** — 依赖 accounts + llm_gateway + knowledge_base
6. **MOD-005 publisher** — 依赖 accounts + content + settings_vault
7. **MOD-006 video_generator** — 依赖 accounts + content + llm_gateway + settings_vault
8. **MOD-007 notifications** — 依赖所有上层模块（最后实现）

## 目录结构

```
src/
├── backend/
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── accounts/
│   │   ├── knowledge_base/
│   │   ├── llm_gateway/
│   │   ├── content/
│   │   ├── publisher/
│   │   ├── video_generator/
│   │   ├── notifications/
│   │   └── settings_vault/
│   ├── core/
│   │   ├── encryption.py    # AES-256-GCM
│   │   ├── permissions.py   # 自定义权限
│   │   └── pagination.py
│   ├── requirements.txt
│   └── manage.py
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── stores/
│   │   ├── views/
│   │   └── router/
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml
└── nginx/
    └── nginx.conf
```
