pre-commit:
	poetry run pre-commit run --all-files

export:
	poetry export --without-hashes > requirements.txt
