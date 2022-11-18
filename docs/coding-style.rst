.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

.. Please, keep sections in alphabet order.
.. Current structure is one item per section, no inner sections. We may re-consider this later,
   though.

.. contents::

Characters per line
===================

We use 100 characters per line. Please, configure your editor to wrap everything to 100 characters
per line.

Each file should include the following vim configuration line: "``vim: ts=4 sw=4 tw=100 et ai si``".
So vim should automatically use 100 characters per line limit. Feel free adding a similar statement
for your favorite editor.

Commentaries
============

#. We always use a dot at the end of a sentence, even for single line commentaries.

   * Example: ``# Calculate CPU frequency.``

Qoutes for strings
==================

Whenever possible, use double quotes. Do not use single quotes, unless you have to.

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

Splitting f-strings
===================

If an f-string needs to be split because it is too long, we use the "f" marker in front of all the
string parts, even if it is not necessary.

*Do*:::

 f"my long f-string {variable}"
 f"no variables in this part"

*Don't*:::

 f"my long f-string {variable}"
 "no variables in this part"
