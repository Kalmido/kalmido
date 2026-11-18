#!/usr/bin/env python3
"""2.991.0 (#5530): the type and spacing scale of the stylesheets (tests/p2419_scale_test.py) as a step of the Lint job.

The check is static (no container, seconds), but as a suite it was soft and ran in the full CI only: red six times
(2.833 ... 2.962) after a package wrote a size, a line height or a gap outside the scale. As a lint step it is red on the
build job's Mac run already and holds the package in the einreihen check (a lint step is always hard). The rules stay in
the test file (one place); this runs it.
usage: python3 tools/check_css_scale.py"""
import os
import runpy
import sys

TESTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")
LINT_WHY = ("a size, line height or gap outside the scale makes areas look different; it slipped through to the full CI "
            "six times")
LINT_INSTEAD = "the steps of the type and spacing scale (tests/p2419_scale_test.py names them)"

if __name__ == "__main__":
    import lintmsg  # tools/ is the script's folder, so it is on the path
    sys.path.insert(0, TESTS)  # tests/kt.py
    sys.argv = [os.path.join(TESTS, "p2419_scale_test.py")]
    with lintmsg.red_hint("check_css_scale", LINT_WHY, LINT_INSTEAD):
        runpy.run_path(sys.argv[0], run_name="__main__")
