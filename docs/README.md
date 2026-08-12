# NexusProtocol console — GitHub Pages

This folder is deployed to GitHub Pages by `.github/workflows/pages.yml`.

It is a fully static, fully working operator console:

- **Demo runtime (default)** — a real policy engine (`engine.js`) runs in the
  browser: policy packs are evaluated, sensitive actions sink into the
  human-approval dip, and every event is written to a hash-chained audit log
  persisted in `localStorage`. No backend, no Docker, no external hosting.
- **Live gateway mode** — the same console drives a running
  `clearframe serve` gateway (or the `platform/` backend) over HTTP: enter the
  gateway URL in the connection bar.

Design language: white paper surface, black ink, neumorphic 3D accents
(raised gates, sunken dips and indents), glassmorphic bars and modals,
monochrome with sparse red/amber/green status accents.

Files:

| File         | Purpose                                              |
| ------------ | ---------------------------------------------------- |
| `index.html` | Sign-in (client-side gate) + "Enter the live demo"   |
| `app.html`   | Console shell — all nine views                       |
| `styles.css` | The design system                                    |
| `engine.js`  | In-browser governance engine (demo runtime)          |
| `app.js`     | Console logic and the demo/live runtime switch       |
