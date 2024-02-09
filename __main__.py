#!/usr/bin/python
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Author: Antti Laakso <antti.laakso@intel.com>

import os
import sys
import zipfile
import tempfile
from pathlib import Path
from pepclibs.helperlibs import ProjectFiles
from pepctool._Pepc import main

if __name__ == "__main__":
    basepath = Path(__file__).parent

    # If the parent is not a regular file, not a zipapp archive.
    if not basepath.is_file():
        sys.exit(main())

    # This is a zipapp archive. It includeds the python code and the data. In order for the data to
    # be found by the tool, it should be extracted somewhere and made accessible to the too via the
    # data path environment variable.

    envvar = ProjectFiles.get_project_data_envvar("pepc")
    if envvar in os.environ:
        # The environment variable is already set, assume the test data are there, nothing to do.
        sys.exit(main())

    # Create a temporary directory and extract tool data there.
    zipapp_path = Path(__file__).parent
    with zipfile.ZipFile(zipapp_path) as zf, tempfile.TemporaryDirectory() as tmpdir:
        # Unzip the data sub-directory.
        for path in zf.namelist():
            if path.startswith("tpmi/"):
                zf.extract(path, tmpdir)

        os.environ[envvar] = tmpdir
        sys.exit(main())
