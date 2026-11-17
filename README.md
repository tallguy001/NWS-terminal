# NWS Terminal

A weather web app on Cloudflare Pages. The repository root is the site: the same files as a release zip (`index.html`, `app.js`, `app.css`, `_worker.js`, `sw.js`, `geo/`, `icons/` and the rest).

## Releases

A push to `main` deploys to Cloudflare Pages through `.github/workflows/deploy.yml`. Before deploying, the workflow checks that the scripts parse, that the version marks in `app.js`, `_worker.js` and `index.html` agree, and that no file holds anything shaped like an API key. A run can also be started by hand from the Actions tab.

To go back to an earlier release, revert the commit on `main`; the revert deploys like any other push.

## One-time setup

In this repository, under Settings > Secrets and variables > Actions:

| Kind | Name | Value |
|---|---|---|
| Secret | `CLOUDFLARE_API_TOKEN` | A Cloudflare API token with Account > Cloudflare Pages > Edit |
| Secret | `CLOUDFLARE_ACCOUNT_ID` | The Cloudflare account ID |
| Variable | `CF_PAGES_PROJECT` | The name of the Pages project (the part before `.pages.dev`) |

## Keys

No API key belongs in this repository. The app's keys are Cloudflare secrets on the Pages project, read only by `_worker.js`: `GS_TOKEN`, `ANTHROPIC_API_KEY`, `WETHR_API_KEY`, `WINDY_WEBCAMS_KEY`, `LIGHTNING_KEY`, `RADAR_TILES_KEY`, `WI511_KEY`, and the optional `APP_PASSCODE`. "Settings & keys" in the app shows which are set.
