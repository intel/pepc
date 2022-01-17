# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides helpers for dealing with jinja2 templates.
"""

import logging
import jinja2
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

def build_jenv(templdir, scheme=0, **kwargs):
    """
    Build a bare minimum Jinja2 environment for templates in the 'templdir' directory. No globals or
    filters are added to the environment.

    The 'scheme' argument selects the Jinja2 delimeters scheme #0 or #1. Scheme #0 uses the normal
    default Jinja2 delimeters like "{{" and "{%". Scheme #1 uses alternative delimeters, which can
    be useful for rendering a single template twice. Here are the scheme #1 delimeters.
       * "<% %>" for block start/end.
       * "<< >>" for variable start/end.
       * "<# #>" for comment start/end.

    The 'kwargs' argumens will be passed as-is to 'jinja2.Environment()', so you can used them for
    passing something like 'trim_blocks=True' and 'lstrip_blocks=True'.
    """

    if scheme == 1:
        kwargs["block_start_string"] = "<%"
        kwargs["block_end_string"] = "%>"
        kwargs["variable_start_string"] = "<<"
        kwargs["variable_end_string"] = ">>"
        kwargs["comment_start_string"] = "<#"
        kwargs["comment_end_string"] = "#>"

    try:
        loader = jinja2.FileSystemLoader(str(templdir)) # Jinja2 does not like pathlib.Path objects.
        return jinja2.Environment(loader=loader,
                                  autoescape=jinja2.select_autoescape(['html', 'htm', 'xml']),
                                  **kwargs)
    except jinja2.TemplateError as err:
        raise Error(f"cannot create Jija2 environment for templates in '{templdir}':\n{err}") \
              from err

def render_template(jenv, templpath, outfile=None):
    """
    Render the "templpath" Jinja2 template file using the 'jenv' environment. Note, if 'templepath'
    does not start with "/", then it is assumed to be relative to the templates directory the 'jenv'
    jinja2 environment was created for. Returns the resulting contents and optionally saves it in
    the "outfile" file.
    """

    if templpath.is_absolute():
        templpath = templpath.resolve().relative_to(jenv.loader.searchpath[0])

    path = jenv.loader.searchpath[0] / templpath
    try:
        # Jinja2 does not like pathlib.Path objects.
        contents = jenv.get_template(str(templpath)).render()
    except jinja2.TemplateError as err:
        raise Error(f"cannot render template '{path}':\n{err}") from err

    _LOG.debug("rendered template '%s'", path)

    if outfile:
        try:
            with open(outfile, "wb") as fobj:
                fobj.write(contents.encode("utf-8"))
        except UnicodeError as err:
            raise Error(f"failed to encode with 'utf-8' before writing to '{outfile}':\n{err}") \
                  from None
        except OSError as err:
            raise Error(f"failed to write to '{outfile}':\n{err}") from None

        _LOG.debug("saved rendered data to '%s'", outfile)

    return contents
