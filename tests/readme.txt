The "v1" tests in this directory will be removed at some point.

Examples for runnint tests.

# List all tests
pytest --collect-only

# Run all tests in 'test_msr.py' module
pytest tests/test_msr.py

# Run a single test called 'test_get'
pytest -k test_get

# Enable debug logs
pytest --log-cli-level=DEBUG

# Disable pytest log capturing and print logs to console instead
pytest -s

# Run for a single emulation dataset, instead of all (default)
pytest -D bdwup0
