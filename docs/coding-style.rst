.. -*- coding: utf-8 -*-
.. vim: ts=4 sw=4 tw=100 et ai si

.. Please, keep sections in alphabet order.

============
Coding Style
============

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

Dot at the end of sentence
++++++++++++++++++++++++++

#. We always use a dot at the end of a sentence, even for single line commentaries.

   * Example: ``# Calculate CPU frequency.``

We try to do document the code and provide useful comments. However, not every comment is useful.
Here are some guidelines.

Commenting the obvious
++++++++++++++++++++++

In other words, don't comment the obvious.

*Don't*:::

 # Increase the counter.
 counter += 1

We can see from the code that we are increasing the counter, no need to explain that in the comment.
Either do not add any comment, or, if it is a tricky place, explain *why* the counter is increased.


Strings
=======

Quoting
+++++++

Whenever possible, use double quotes. Do not use single quotes, unless you have to.

*Do*:

* ``"my string"``
* ``mydict["element"]``
* ``if "a" in data:``

*Don't*:

* ``'my string'``
* ``mydict['element']``
* ``if 'a' in data:``

Possible exceptions example:

* ``f"dictionary element {mydict['element']}"``

Splitting f-strings
+++++++++++++++++++

If an f-string needs to be split because it is too long, we use the "f" marker in front of all the
string parts, even if it is not necessary.

*Do*:::

 f"my long f-string {variable}"
 f"no variables in this part"

*Don't*:::

 f"my long f-string {variable}"
 "no variables in this part"

Code separators
===============

To separate and categorize functions we sometimes use separators, these help to distinguish
functions that have the same overarching theme. Here is an example:

::

   # ------------------------------------------------------------------------------------------------ #
   # Getting functions.
   # ------------------------------------------------------------------------------------------------ #

      def get_cpu_turbo(self, cpu):
         ...

      def get_cpu_frequency(self, cpu):
         ...

   # ------------------------------------------------------------------------------------------------ #
   # Setting functions.
   # ------------------------------------------------------------------------------------------------ #

      def set_cpu_turbo(self, cpu):
         ...

      def set_cpu_frequency(self, cpu):
         ...

   # ------------------------------------------------------------------------------------------------ #
