"""Driftwire: catches what silently changed between two releases of a dataset, maps it to the analyses and research
questions it affects, and hands a person the decision. Research use only.

The implementation lives in the `tripwire` package (the project's working name); this package is the public name.
`python -m driftwire ...` and `python -m tripwire ...` run the same tool.
"""
from tripwire import __version__  # noqa: F401
from tripwire.api import Result, check  # noqa: F401,E402  driftwire.check(trusted, new, question=...)
