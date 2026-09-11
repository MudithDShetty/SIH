# Host BeamLock on Netlify (for SIH judges)

## Important limit

Netlify serves **static websites**. It cannot run the full desktop prototype
(`python main.py` / Pygame / YOLO / OpenCV).

This folder publishes:

| URL path | What judges get |
|---|---|
| `/` | Landing page (SIH26169, how to run full app) |
| `/demo.html` | Interactive browser mini-demo (usable in any browser) |
| `/architecture.html` | Interactive architecture diagram |

Full Classical / AI+fusion / Streamlit evaluation still runs from GitHub on a laptop.

## Deploy (one-time)

### Option A — Netlify UI (easiest)

1. Push this repo to GitHub (already: `MudithDShetty/SIH`).
2. Go to [https://app.netlify.com](https://app.netlify.com) → **Add new site** → **Import from Git**.
3. Select the repo.
4. Build settings:
   - **Base directory:** `fsoc-virtual-tracker`  
     (or leave blank if Netlify root is already that folder)
   - **Build command:** leave empty / `echo ok`
   - **Publish directory:** `site`  
     (if base is repo root: `fsoc-virtual-tracker/site`)
5. Deploy. Copy the `*.netlify.app` URL into your PPT / submission.

### Option B — Netlify CLI

```bash
cd fsoc-virtual-tracker
npx netlify login
npx netlify init
npx netlify deploy --prod --dir=site
```

`netlify.toml` in this folder already sets `publish = "site"`.

## Local preview

```bash
cd fsoc-virtual-tracker/site
python -m http.server 8080
```

Open `http://localhost:8080`.

## Do not break the desktop app

Do not replace `main.py` with web code. The Netlify site is additive under `site/`.
