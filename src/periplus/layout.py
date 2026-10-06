"""Where a project keeps its Periplus files. Three names, one home.

These lived in ``settings.py`` and ``packs.py``, which is where they are used most, and that is
where they would have stayed had nothing else needed them. ``init.py`` needs all three to create
the tree, which makes three modules reading one fact.

One home is what keeps the three readings identical. The alternative was re-spelling the three
strings inside ``init.py``, which is the drift this package refuses everywhere else it duplicates a
constant on purpose — a project marker spelled two ways is a tree one module creates and another
cannot find.

``settings.py`` and ``packs.py`` import from here and keep exporting the names they always
exported, so every existing caller is unchanged.
"""

from __future__ import annotations

__all__ = ["PACKS_DIRECTORY", "PROJECT_MARKER", "SETTINGS_FILENAME"]

#: The directory whose presence marks a project root, and the file inside it. A directory rather
#: than a file, for the reason ``git`` looks for ``.git`` — the same directory holds the settings
#: file and the project's own packs, so one marker answers both.
PROJECT_MARKER = ".periplus"
SETTINGS_FILENAME = "settings.yml"

#: The pack directory's name, under a project root's marker directory and under the user
#: configuration directory alike. One name, so the two roots cannot drift apart.
PACKS_DIRECTORY = "packs"
