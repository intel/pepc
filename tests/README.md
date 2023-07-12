# Examples for running tests

List all tests
* ```pytest --collect-only```

Run all tests in 'test_msr.py' module
* ```pytest tests/test_msr.py```

Run a single test called 'test_msr_read'
* ```pytest -k test_msr_read```

Enable debug logs
* ```pytest --log-cli-level=DEBUG```

Disable pytest log capturing and print logs to console instead
* ```pytest -s```

Run for a single emulation dataset, instead of all (default)
* ```pytest -D bdwup0```

# Test data

Special cases:
* 'bdwex0_noidle' has '```cpuidle.off=1```' boot parameter.
