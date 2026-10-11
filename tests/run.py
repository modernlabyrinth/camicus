"""Run only this repository's tests, with no installed test dependencies."""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
names = sys.argv[1:]
if any(not re.fullmatch(r"test_[a-z_]+", name) for name in names):
    raise SystemExit("Use test module basenames only.")
loader = unittest.TestLoader()
suite = (loader.loadTestsFromNames(["tests." + name for name in names]) if names
         else loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT)))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
