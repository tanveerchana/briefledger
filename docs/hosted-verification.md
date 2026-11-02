# Hosted verification — 2 November 2026

- Public app: https://briefledger.onrender.com/
- Published runtime: `e00f6cbb25abe29d6d78557327cd187946b1abd0`.
- Render service: `srv-dbjujg8ae00c73fark7g`; free Python service in Singapore.
- Render deploy `dep-dbk42pe7bikc739328ig` reached `live`.
- `/healthz` returned HTTP 200 with `{"status":"ok","service":"briefledger"}`.
- GitHub Actions [run 41408997129](https://github.com/tanveerchana/briefledger/actions/runs/41408997129) passed on both Python 3.12 and 3.13: dependency installation, Ruff lint/format, all 45 pytest tests and compileall. The pytest root path is configured explicitly; tests were not skipped.
- In the public browser, `access reviews` returned two source excerpts. Opening the policy result displayed the original source with line numbers and the cited range 1–26.
- Pasted a synthetic Markdown source, observed the collection increase from four to five sources, and searched its unique `zephyr` token.
- The temporary-storage notice was visible. A deploy actually reset the browser collection; reloading renewed it with the four sample sources. This is evidence of ephemeral hosting, not durable cloud persistence.

No real user documents or third-party credentials were used. Recent Render error logs were empty at verification. This verifies boot, readiness and the sampled browser workflow, not production load, indefinite availability or durable storage. Free instances idle and can take time to wake. No paid disk or database was provisioned.
