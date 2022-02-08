Quick quide for using 'pytest'

# List all tests
pytest --collect-only

# Run all tests in 'test_msr.py' module
pytest -k tests/test_msr.py

# Run single test called 'test_get'
pytest -k test_get

# Enable debug logs
pytest --log-cli-level=DEBUG

# Disable pytest log capturing and print logs to console instead.
pytest -s
