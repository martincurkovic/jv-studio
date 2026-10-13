"""Entry point for built apps (pyside6-deploy compiles this file, as AKAISDS does with its src/main.py).

From a checkout, `uv run jv-studio` or `python -m jv_studio` do the same thing.
"""

from jv_studio.main import main

if __name__ == "__main__":
    raise SystemExit(main())
