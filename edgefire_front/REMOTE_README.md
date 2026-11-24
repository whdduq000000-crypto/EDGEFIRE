# EDGE-FIRE remote integration

The demo-integration branch already includes the `/remote` route, LiveTelemetry, a copy of the original Cesium map with live markers, and a server-side API proxy. **Do not run `patch_team_frontend.py` again on this branch.** The original `/` page remains unchanged. For a clean copy of main, use the patch script; for the AI integration branch, follow `../EDGEFIRE_backend_remote/docs/REMOTE_SETUP.md` instead.

Create `.env.local` locally using `../EDGEFIRE_backend_remote/adapters/frontend/env.local.example`; set the actual BE Tailscale IP and UI API token, never commit secrets. Use `npm ci`, `npm run build`, then `npm run dev -- --hostname 127.0.0.1 --port 3200`. Open http://127.0.0.1:3200/remote. Full Next.js build and remote network still need verification. Existing example `/` is not the live dashboard.
