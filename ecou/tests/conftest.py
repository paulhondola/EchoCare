import sys
from pathlib import Path

# The app's modules live where App Lab expects them, not in a package
sys.path.insert(0, str(Path(__file__).parents[1] / "app" / "python"))
