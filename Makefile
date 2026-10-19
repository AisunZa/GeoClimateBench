.PHONY: install demo test grade clean
install:
	python -m pip install -e '.[dev]'
demo:
	python -m geoclimatebench demo --data-dir data --output results
test:
	python -m pytest -q
grade:
	python -m geoclimatebench grade --data-dir data --output results
clean:
	rm -rf data results .pytest_cache *.egg-info
