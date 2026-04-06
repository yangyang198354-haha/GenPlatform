<file_header>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <timestamp>2026-04-06T01:40:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>architecture/architecture_design.md (APPROVED)</file>
    <file>architecture/tech_stack.md (APPROVED)</file>
    <file>testing/unit_test_report.md (APPROVED)</file>
    <file>testing/integration_test_report.md (APPROVED)</file>
    <file>testing/e2e_test_report.md (APPROVED)</file>
  </input_files>
  <phase>PHASE_10</phase>
  <status>APPROVED</status>
</file_header>

# CI/CD 流水线设计 — 内容生成平台

## 流水线概览（GitHub Actions）

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  # ── Stage 1: Lint & Static Analysis ─────────────────────────
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install ruff bandit safety
      - run: ruff check src/backend/        # Style check
      - run: bandit -r src/backend/apps/    # Security check
      - run: safety check -r src/backend/requirements.txt  # CVE check

  # ── Stage 2: Backend Unit Tests ──────────────────────────────
  test-unit:
    runs-on: ubuntu-latest
    needs: lint
    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_DB: test_db
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - run: |
          cd src/backend
          pip install -r requirements.txt
          pytest apps/ --cov=apps --cov-report=xml --cov-fail-under=80 -x
      - uses: codecov/codecov-action@v4

  # ── Stage 3: Integration Tests ───────────────────────────────
  test-integration:
    runs-on: ubuntu-latest
    needs: test-unit
    services:
      postgres:
        image: pgvector/pgvector:pg15
        env: { POSTGRES_DB: test_db, POSTGRES_PASSWORD: postgres }
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - run: |
          cd src/backend
          pip install -r requirements.txt
          pytest apps/ -m integration --cov-fail-under=90

  # ── Stage 4: Frontend Build ───────────────────────────────────
  build-frontend:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: |
          cd src/frontend
          npm ci
          npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: frontend-dist
          path: src/frontend/dist/

  # ── Stage 5: Docker Build & Push ─────────────────────────────
  docker-build:
    runs-on: ubuntu-latest
    needs: [test-integration, build-frontend]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: src/backend
          push: true
          tags: ghcr.io/${{ github.repository }}/backend:${{ github.sha }}
      - uses: docker/build-push-action@v5
        with:
          context: src/frontend
          push: true
          tags: ghcr.io/${{ github.repository }}/frontend:${{ github.sha }}

  # ── Stage 6: Deploy to Staging ───────────────────────────────
  deploy-staging:
    runs-on: ubuntu-latest
    needs: docker-build
    environment: staging
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: deploy
          key: ${{ secrets.STAGING_SSH_KEY }}
          script: |
            cd /opt/content-gen-platform
            docker compose pull
            docker compose up -d --wait
            docker compose exec backend python manage.py migrate
```

## 环境矩阵

| 环境 | 触发条件 | 自动/手动 |
|------|---------|---------|
| 开发 | feature 分支 push | 自动 lint + unit test |
| Staging | main 分支 merge | 自动全流水线 + 自动部署 |
| 生产 | 手动触发（需人工确认） | 手动（PRODUCTION_DEPLOY_CONFIRM） |
