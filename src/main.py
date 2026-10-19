"""Entry point for built apps (pyside6-deploy compiles this file, as AKAISDS does with its src/main.py).

From a checkout, `uv run jv-studio` or `python -m jv_studio` do the same thing.
"""

import sys
import traceback


def _smoke_report_path(argv):
    for arg in argv[1:]:
        if arg.startswith("--smoke-test="):
            return arg.partition("=")[2] or None
    return None


def _run():
    from jv_studio.main import main

    return main()


if __name__ == "__main__":
    try:
        code = _run()
    except Exception:
        # A built Windows app has no console, so a failure before the smoke test's own report (an import that didn't get bundled, a Qt plugin that
        # won't load) would otherwise leave CI with an exit code and nothing else: put the traceback where CI looks.
        report = _smoke_report_path(sys.argv)
        if report:
            with open(report, "w", encoding="utf-8") as f:
                f.write("SMOKE TEST CRASHED BEFORE ITS REPORT\n" + traceback.format_exc())
        raise
    raise SystemExit(code)
