---
title: NexusProtocol
emoji: "\U0001F310"
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 8080
pinned: false
---

# NexusProtocol on Hugging Face Spaces

Free, permanent, no AWS. To deploy:

1. Create a new Space → **Docker** → **Blank**.
2. In the Space repo, add this repo's contents (or add this repo as a remote and
   push). The Space builds `Dockerfile` at the root automatically.
3. Put this file's front-matter (the block above, between the `---` lines) at the
   top of the Space's `README.md` so Spaces routes to port 8080.

The Space URL (e.g. `https://<user>-nexusprotocol.hf.space`) serves the full
console: create agents, run the governed loop, Aegis HITL, Sonar, Trust
Registry, benchmark — all live, same-origin.
