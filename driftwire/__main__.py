"""python -m driftwire: the Driftwire command line (same tool as python -m tripwire)."""
import sys

from tripwire.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
