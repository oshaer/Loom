# Loom on the web

`index.html` runs Loom RL in a web browser. It holds the `loomrl` Python sources and runs them
with [Pyodide](https://pyodide.org), so the browser and terminal versions run the same code.
Nothing is sent anywhere; the simulation runs on the viewer's device.

- **Open it:** any static host works, including GitHub Pages. Locally, run
  `python -m http.server` in this folder and visit http://localhost:8000. (Opening the file
  directly also works in most browsers.)
- **After changing `loomrl`:** rebuild the page with `python build.py`. It reads
  `../loomrl/loomrl`, `driver.py` and `template.html` and writes `index.html`.

## Files

| file | role |
|---|---|
| `index.html` | the built page (open or host this one) |
| `template.html` | page layout, controls and the code that draws each frame |
| `driver.py` | steps the simulation one tick at a time for the page |
| `build.py` | puts the sources into the template to make `index.html` |

On the page: choose a maze size and number, the number of buggles and faulty buggles, and
whether trust is on. **Play/Pause**, **Step**, **Skip round** and **Run to end** control the run;
**Speed** sets ticks per second. When the run ends, the plain-English log appears with
**Copy log** and **Download log** buttons.
