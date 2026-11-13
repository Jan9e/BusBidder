import sys
from .cli import main

try:
    sys.exit(main())
except KeyboardInterrupt:
    print("\nInterrupted. Goodbye.")
    sys.exit(130)