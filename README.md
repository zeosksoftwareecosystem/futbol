# Football Live Scanner

Standalone Streamlit project. It does not import or reuse the previous football application.

## Run locally
```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Open data sources
- ESPN public soccer scoreboard endpoint: no API key required, unofficial/undocumented and subject to change. Competition coverage varies.
- OpenFootball JSON: open community dataset for fixtures/results; static, not a live-stat feed.

No paid API, user API key, or mock data is used.

## Important limitations
- The initial version retrieves scoreboards from a curated list of ESPN competition slugs. It cannot guarantee every competition worldwide.
- Match summary/statistics parsing is not yet enabled because ESPN's summary schema varies by competition and the public endpoint must be validated against actual events. Unsupported statistics remain N/A.
- 5/10-minute deltas are intentionally N/A until two timestamped observations actually bracket those periods. Repeated Streamlit scans create snapshots; they are not reconstructed from cumulative match totals.
- Goal/corner pressure scores are heuristic 0–100 indicators, not probabilities. Confidence indicates the share of available weighted inputs.
- Browser automation and ScraperFC are not dependencies.

## Deploy
Upload the project files to a new GitHub repository and deploy `app.py` as a new Streamlit app. Keep the old app untouched.
