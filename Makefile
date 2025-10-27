.PHONY: dev-up dev-down dev-logs test audit lint

dev-up:
	@echo "Bringing up dev environment..."
	@docker compose --profile dev up --build -d

dev-down:
	@echo "Tearing down dev environment..."
	@docker compose --profile dev down

dev-logs:
	@echo "Tailing logs..."
	@docker compose logs -f

test:
	@echo "Running tests..."
	@docker compose run --rm vna uv run pytest

audit:
	@echo "Running pip-audit..."
	@docker compose run --rm vna uv run pip-audit

lint: audit
	@echo "Running lints..."
	# Add other linting commands here in the future
	@echo "Linting complete."
