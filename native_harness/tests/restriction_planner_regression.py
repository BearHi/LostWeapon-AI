"""Ban fields must not be mistaken for movement devices or reward sources."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from global_planner import GlobalMapPlanner

width, height = 24, 18
grid = [0] * (width * height)
for x in range(1, 23):
    grid[14 * width + x] = 1
records = [(100, 2, 13), (140, 20, 13), (136, 5, 13), (138, 13, 13)]
planner = GlobalMapPlanner(width, height, records, grid)
assert planner.mechanic_profile()["mode"] == "platform"
assert planner.mechanic_profile()["object_ids"] == []
print("PASS: restriction blocks do not create transport reward")
