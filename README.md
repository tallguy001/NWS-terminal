# NWS Terminal

A weather web app on Cloudflare Pages (project `nws4`). The repository root is the site: the same files as a release zip (`index.html`, `app.js`, `app.css`, `_worker.js`, `sw.js`, `geo/`, `icons/` and the rest).

## Releases

The Pages project is connected to this repository. A push to `main` is deployed to production by Cloudflare; a push to any other branch gets its own preview address. There is no build step: the files are served as they are.

To go back to an earlier release, revert the commit on `main`; the revert deploys like any other push.

## Keys

No API key belongs in this repository, which is public. The app's keys are Cloudflare secrets on the Pages project, read only by `_worker.js`: `GS_TOKEN`, `ANTHROPIC_API_KEY`, `WETHR_API_KEY`, `WINDY_WEBCAMS_KEY`, `LIGHTNING_KEY`, `RADAR_TILES_KEY`, `WI511_KEY`, and the optional `APP_PASSCODE`. "Settings & keys" in the app shows which are set.
