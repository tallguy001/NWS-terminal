# NWS Terminal

A weather web app on Cloudflare Pages (project `nws4`). The repository root is the site: the same files as a release zip (`index.html`, `app.js`, `app.css`, `_worker.js`, `sw.js`, `geo/`, `icons/` and the rest).

## Releases

The Pages project is connected to this repository. A push to `main` is deployed to production by Cloudflare; a push to any other branch gets its own preview address. There is no build step: the files are served as they are.

To go back to an earlier release, revert the commit on `main`; the revert deploys like any other push.

## Keys

No API key belongs in this repository, which is public. The app's keys are Cloudflare secrets on the Pages project, read only by `_worker.js`: `GS_TOKEN`, `ANTHROPIC_API_KEY`, `WETHR_API_KEY`, `WINDY_WEBCAMS_KEY`, `LIGHTNING_KEY`, `RADAR_TILES_KEY`, `WI511_KEY`, and the optional `APP_PASSCODE`. "Settings & keys" in the app shows which are set.

## Tests

`tests/` and `.github/` are for testing and are not served as part of the site.

- `node tests/smoke.cjs --base https://nws4.pages.dev` opens the app in a real browser and walks it: the US map, a place, every section, a few maps, Settings, three screen sizes. It fails on a script error, a blank section, sideways scroll or the wrong version; a slow data source is only a warning. `--local .` tests the files in this folder laid over the live site.
- `node tests/worker-errors.test.mjs` tests the Worker's error-log routes against a stand-in store.

Both run on every push, on any branch, at the address Cloudflare gives that branch (GitHub, Actions, "Screen tests").

## Error log

The app reports its own script errors to `/api/err`, and `/api/errors` lists them (also in Settings, under App health). A row holds the message, file and line, section, kind of device and version, never a place or a coordinate. The list can be read by anyone with the address unless `APP_PASSCODE` is set.
