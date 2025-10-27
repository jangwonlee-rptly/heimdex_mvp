dev-up:
	docker compose --profile dev up -d


dev-down:
	docker compose --profile dev down -v


test:
	docker compose exec vna uv run pytest -q
