pre-commit:
	poetry run pre-commit run --all-files

ts:
	flask ts > app/templates/types.d.ts

export:
	poetry export --without-hashes > requirements.txt
