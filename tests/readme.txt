# Examples for running tests.

# List all tests
pytest --collect-only

# Run all tests in 'test_msr.py' module
pytest tests/test_msr.py

# Run a single test called 'test_msr_read'
pytest -k test_msr_read

# Enable debug logs
pytest --log-cli-level=DEBUG

# Disable pytest log capturing and print logs to console instead
pytest -s

# Run for a single emulation dataset, instead of all (default)
pytest -D bdwup0

# Testdata is collected using the 'tdgen' -tool. By default, testdata is collected with BIOS
# settings documented in SUT wiki: https://intelpedia.intel.com/ServerPowerLab/Hardware/SUTs.

# Exeption is 'spr0_nomwait' dataset, where MWAIT was disabled by changing following setting:
# EDKII Menu ->
# Socket Configuration ->
# Advanced Power Management Configuration ->
# CPU C State Control ->
# Enable Monitor MWAIT -> Disable
