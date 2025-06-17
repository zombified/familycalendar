pip-compile:
	./env/bin/pip-compile -o requirements.txt pyproject.toml

run:
	./env/bin/familycal dev.toml
