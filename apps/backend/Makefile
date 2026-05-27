.PHONY: dev start stop test lint format clean

PORT ?= 8001
HOST ?= 0.0.0.0

# 最简单的启动命令（开发模式，热重载）
dev:
	@uv run uvicorn app.main:app --host $(HOST) --port $(PORT) --reload

# 生产模式启动
start:
	@uv run uvicorn app.main:app --host $(HOST) --port $(PORT)

# 停止占用端口的进程
stop:
	@lsof -ti:$(PORT) | xargs kill -9 2>/dev/null && echo "Port $(PORT) freed" || echo "Port $(PORT) not in use"

# 运行测试
test:
	@uv run pytest -v

# 代码格式化
format:
	@uv run black app/ tests/
	@uv run isort app/ tests/

# 代码检查
lint:
	@uv run pylint app/
	@uv run mypy app/

# 清理缓存
clean:
	@rm -rf __pycache__ .pytest_cache .mypy_cache
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned up cache files"

# 帮助
help:
	@echo "Available commands:"
	@echo "  make dev         - Start development server with hot reload"
	@echo "  make start       - Start production server"
	@echo "  make stop        - Kill process on port $(PORT)"
	@echo "  make test        - Run tests"
	@echo "  make format      - Format code with black and isort"
	@echo "  make lint        - Run pylint and mypy"
	@echo "  make clean       - Clean cache files"
	@echo ""
	@echo "Docker 镜像: 系统启动时会全自动管理，无需手动操作"
	@echo "  - 自动检测、构建、加载、保存"
	@echo "  - 查看状态: curl http://localhost:8000/health/docker"
	@echo ""
	@echo "Options:"
	@echo "  make dev PORT=8001  - Use different port"
