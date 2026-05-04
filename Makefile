.PHONY: setup up down migrate reset-db reset-db-hard shell serve worker lint test format clean

# Initial project setup
setup:
	uv sync
	docker-compose up -d
	sleep 3
	uv run python manage.py migrate
	@echo "Setup completed. Use 'make serve' to start the server."

# Start base infrastructure (DB, Redis)
up:
	docker-compose up -d

# Stop infrastructure
down:
	docker-compose down

# Database
migrate:
	uv run python manage.py makemigrations
	uv run python manage.py migrate

# Reset the database
reset-db:
	docker-compose up -d db
	@until docker-compose exec -T db pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
	docker-compose exec -T db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS pets_db WITH (FORCE);"
	docker-compose exec -T db psql -U postgres -d postgres -c "CREATE DATABASE pets_db OWNER postgres;"
	@echo "Database reset complete."

# Servers
serve:
	uv run python manage.py runserver

worker:
	uv run celery -A config worker --loglevel=info

shell:
	uv run python manage.py shell

# Code quality
format:
	uv run ruff format .

lint:
	uv run ruff check . --fix
	uv run mypy .

test:
	uv run pytest --cov=core --cov-report=html

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .ruff_cache/ .mypy_cache/ .pytest_cache/ htmlcov/ .coverage
