DC = docker-compose run --rm penny

.PHONY: up kill fmt lint fix typecheck check

up:
	docker-compose up --build

kill:
	docker-compose down --rmi local --remove-orphans

fmt:
	$(DC) ruff format penny/

lint:
	$(DC) ruff check penny/

fix:
	$(DC) ruff format penny/
	$(DC) ruff check --fix penny/

typecheck:
	$(DC) ty check penny/

check:
	$(DC) ruff format --check penny/
	$(DC) ruff check penny/
	$(DC) ty check penny/
