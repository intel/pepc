# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
A dummy 'paramiko' module for systems where 'paramiko' is not available. This allows the tools to
function correctly on the local host, where 'paramiko' is not required.

Provide dummy implementations of the classes and methods used by the project. All dummy versions
simply raise an exception if called.
"""

from __future__ import annotations # Remove when switching to Python 3.10+.

import typing

if typing.TYPE_CHECKING:
    from typing import Tuple

class AuthenticationException(Exception):
    """"A dummy version of 'paramiko.ConfigParseError'."""

class ConfigParseError(Exception):
    """"A dummy version of 'paramiko.ConfigParseError'."""

class SSHConfig:
    """A dummy version of 'paramiko.SSHConfig'."""

    def __init__(self):
        """A dummy version of 'paramiko.SSHConfig.__init__()'."""
        raise NotImplementedError("paramiko is not available")

    def from_path(self, _: str) -> SSHConfig:
        """A dummy version of 'paramiko.SSHConfig.from_path()'."""
        raise NotImplementedError("paramiko is not available")

class SSHClient:
    """A dummy version of 'paramiko.SSHClient'."""

    def __init__(self):
        """A dummy version of 'paramiko.SSHClient.__init__()'."""
        raise NotImplementedError("paramiko is not available")

    def set_missing_host_key_policy(self, _: AutoAddPolicy):
        """A dummy version of 'paramiko.SSHClient.set_missing_host_key_policy()'."""
        raise NotImplementedError("paramiko is not available")

    def connect(self, *_: Tuple[str, int, str, str]):
        """A dummy version of 'paramiko.SSHClient.connect()'."""
        raise NotImplementedError("paramiko is not available")

    def get_transport(self):
        """A dummy version of 'paramiko.SSHClient.get_transport()'."""
        raise NotImplementedError("paramiko is not available")

class AutoAddPolicy:
    """A dummy version of 'paramiko.AutoAddPolicy'."""

    def __init__(self):
        """A dummy version of 'paramiko.AutoAddPolicy.__init__()'."""
        raise NotImplementedError("paramiko is not available")
