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
* 'spr2' has '```idle=nomwait```' boot parameter.
* 'bdwex0' has '```cpuidle.off=1```' boot parameter.

# msr-ioscope

The 'msr-ioscope' tool can be used for finding out the MSR I/O scope. Run:

tests/msr-ioscope all
