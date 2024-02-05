# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""
This feature includes the "tpmi" 'pepc' command implementation.
"""

import os
import logging
from pathlib import Path
from pepclibs import Tpmi
from pepclibs.helperlibs import ProjectFiles

# Users can define this environment variable to extend the default spec files.
_SPECS_PATH_ENVVAR = "PEPC_TPMI_DATA_PATH"

_LOG = logging.getLogger()

def _find_spec_dirs():
    """Find paths to TPMI specs directories and return them as a list."""

    spec_dirs = []

    # Add the user-defined spec files directory. This directory is optional and can be used for
    # extending the standard spec files.
    path = os.getenv(_SPECS_PATH_ENVVAR)
    if path:
        path = Path(path)
        if not path.exists():
            _LOG.warning("TPMI spec files path '%s' specified in the '%s' environment "
                         "variable does not exist, ignoring it", path, _SPECS_PATH_ENVVAR)
        else:
            spec_dirs.append(path)

    # Find the standard spec-files.
    spec_dirs.append(ProjectFiles.find_project_data("pepc", "tpmi", what="TPMI spec files"))

    return spec_dirs

def tpmi_ls_command(args, pman):
    """
    Implements the 'tpmi info' command. Arguments are as follows.
      * args - command line arguments.
      * pman - process manager.
    """

    spec_dirs = _find_spec_dirs()
    tpmi_obj = Tpmi.Tpmi(spec_dirs, pman)

    features, no_specs = tpmi_obj.get_features()
    if features:
        print("Following features are fully supported:")
        txt = ", ".join(features)
        print(f"  {txt}")
    if no_specs and args.all:
        print("Following features are supported by hardware, but have no spec data available:")
        txt = ", ".join(no_specs)
        print(f"  {txt}")
