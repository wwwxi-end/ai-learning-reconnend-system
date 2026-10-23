import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'routes/api.py'), 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("=== Current api.py content (lines 17-40) ===")
for i, line in enumerate(lines[16:40], start=17):
