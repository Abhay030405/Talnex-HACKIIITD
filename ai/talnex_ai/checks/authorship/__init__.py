"""Authorship proof (architecture section 30): for every claim, find the code behind the feature and read its history on GitHub.

`locate.py` (A1) maps each claim to files and line ranges, `symbols.py` is the code structure it reads, `read.py` (A3) works out who
wrote those lines and when, and the four flags. `identity.py` says whose account counts as "ours"; `store.py` reads and writes the rows.
The history itself (A2, blame and commits) is read by Go through the official GitHub API.
"""
