pre-commit:
	poetry run pre-commit run --all-files

ts:
	flask ts > app/templates/types.d.ts

tests:
	PYTHONPATH='..' python -m unittest

export:
	poetry export --without-hashes > requirements.txt

build:
	poetry build

generate:
	PYTHONPATH='..' python -m tests.test_typescript > tests/resources/tstext.ts

mypy:
	~/miniconda3/envs/py311/bin/mypy .

.PHONY: tests export ts pre-commit generate mypy
