# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains misc. helper functions related to file-system operations.
"""

import time
import logging
from pepclibs.helperlibs import ProcessManager, Human
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

def wait_for_a_file(path, interval=1, timeout=60, pman=None):
    """
    Wait for a file or directory to get created. The arguments are as follows.
      * path - path to the file of directory to wait for.
      * interval - the interval in seconds to poll for 'path'.
      * timeout - for how many seconds to poll until raising an exception.
      * pman - the process manager object defining the host 'path' resides on (local host by
               default).

    Periodically poll for the file or directory at 'path' every 'interval' seconds. If the file does
    not get created within 'timeout' seconds, raise an exception.
    """

    with ProcessManager.pman_or_local(pman) as wpman:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if wpman.exists(path):
                return
            time.sleep(interval)

        interval = Human.duration(timeout)
        raise Error(f"file '{path}' did not appear{wpman.hostmsg} within '{interval}'")
