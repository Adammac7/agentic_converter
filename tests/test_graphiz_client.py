import requests
from pathlib import Path

dot_code = Path(__file__).parent / "example.txt"

body = {
  "graph": dot_code.read_text(),
  "layout": "dot",
  "format": "svg"
}

r = requests.post('https://quickchart.io/graphviz', json=body)

# r.text is sufficient for SVG. Use `r.raw` for png images
svg = r.text

with open(Path(__file__).parent / "output.svg", "w") as f:
    f.write(svg)
