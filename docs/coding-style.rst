.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si


Strings
=======

Whenever possible, use double quotes for strings. Do not use single quotes, unless you have to.
Examples.

*Do*:

* ``"my string"``
* ``mydict["element"]``
* ``if "a" in data:``

*Don't*:

* ``'my string'``
* ``mydict['element']``
* ``if 'a' in data:``

Possible exceptoins example:

* ``f"dictionary elemeht {mydict['element']}"``

Commentaries
============

#. We always use a dot at the end of a sentence, even for single line commentaries.

   * Example: ``# Calculate CPU frequency.``
