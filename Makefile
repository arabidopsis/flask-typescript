pre-commit:
	poetry run pre-commit run --all-files

ts:
	flask ts > app/templates/types.d.ts

tests:
	PYTHONPATH='..' python -m unittest

export:
	poetry export --without-hashes > requirements.txt

.PHONY: tests export ts pre-commit
