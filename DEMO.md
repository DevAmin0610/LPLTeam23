# Running the ClearPath demo

ClearPath checks a client's transfer paperwork (client profile, transfer application, account statement) for problems before it's submitted: missing fields, mismatched SSNs or account numbers, and address differences. A reviewer accepts or dismisses each finding.

The new part is **review memory**. When a reviewer ticks **Remember this decision**, ClearPath saves the _kind_ of finding and the decision (never names, numbers or notes). The next time the same kind of finding shows up in another case, ClearPath shows how reviewers decided it before. It never changes or hides a finding; the reviewer still makes every call.

Everything uses **synthetic data only**. This is a hackathon prototype, not LPL policy and not a compliance guarantee.

## 1. One-time setup

From the repository root, on the `dev` branch:

```sh
git switch dev
git pull
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cp .env.example .env
npm ci
npm --prefix frontend ci
```

Requirements: Python 3.11+, Node.js 22.12+, npm.

Check the backend:

```sh
npm run test:backend    # expect 13 passed
```

## 2. Start it

You need two terminals, both in the repository root. Leave both running.

**Terminal 1, backend:**

```sh
rm -rf local-data       # optional: start with no old cases or lessons
.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

**Terminal 2, frontend.** Pick the option that matches where you're running.

### Option A: on your own laptop

```sh
npm --prefix frontend run dev
```

Open **http://localhost:5173** (use `localhost`, not `127.0.0.1`).

### Option B: on the workshop machine (CloudFront)

The workshop serves each port under a path, like `https://<id>.cloudfront.net/ports/5173/`. The dev server can't run under a path, so build the site with relative paths and serve the build instead.

Replace `<id>` with your workshop address (the part before `.cloudfront.net` in your browser bar):

```sh
echo "VITE_API_BASE_URL=https://<id>.cloudfront.net/ports/8000" > frontend/.env
npm --prefix frontend run build -- --base=./
cd frontend
npx vite preview --host 0.0.0.0 --port 5173 --strictPort
```

Open **https://&lt;id&gt;.cloudfront.net/ports/5173/** (keep the trailing slash).

- `frontend/.env` is machine-specific and already ignored by Git. Don't commit it.
- After any frontend code change, rerun the build and preview commands; the built site doesn't update live.

**It's working when** the green banner at the top says "Demo mode — local extraction and simulated AI explanations." That text comes from the backend.

## 3. Walk through the demo (about 2 minutes)

| Step | Do this                                                                 | What you should see                                                                                                                                                                |
| ---- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Pick **Conflicting details**, click **Load sample case**                | Three findings: SSN, account number and address don't match across the forms. Click a finding's document link to open that page.                                                   |
| 2    | Open **What the explanation provider sees** at the bottom               | The data the AI sees is masked outcomes only: no SSNs, names or account numbers.                                                                                                   |
| 3    | Pick **Formatting differences**, click **Load sample case**             | One finding, **"Address differs only by abbreviations or punctuation."** One form says "Ln," another "Lane." Its **Review memory** note says no past reviews yet.                  |
| 4    | Tick **Remember this decision for similar findings**, click **Dismiss** | **What ClearPath has learned** now shows 1 decision for that kind of finding.                                                                                                      |
| 5    | Click **Load sample case** again (still Formatting differences)         | A new case. The Review memory note turns blue: **"Reviewers dismissed this in 1 of 1 past case. Likely a false alarm, but you make the call."** The finding itself is still shown. |
| 6    | Pick **Conflicting details** and load it again                          | Its address finding is **"Address is a different location"** with no history. A real difference is a different kind of finding, so the lesson doesn't apply.                       |
| 7    | Click **Reset memory**                                                  | Lessons are cleared, ready for the next run.                                                                                                                                       |

The point: memory tells a harmless formatting slip from a real problem, only learns from decisions a reviewer explicitly approves, stores no client data, and never overrides the reviewer.

Other samples to try: **Complete and consistent** (no findings) and **Missing information** (blank fields on the transfer form).

## 4. How it works (short version)

- `backend/app/services/rules.py`: each finding gets a **pattern**, the kind of finding with no values in it (e.g. `ADDRESS_REVIEW:formatting_only` vs `ADDRESS_REVIEW:different`).
- `backend/app/services/memory.py`: stores approved decisions per pattern and builds the history and hint shown on each finding.
- Storage: a `memory` table in the local SQLite file in demo mode; one item (`memory#v1`) in the existing DynamoDB table in AWS mode. No new AWS resources.
- API: `GET /api/memory` (what's been learned), `POST /api/memory/reset` (clear it). The review endpoint takes `"remember": true`.
- Sample PDFs live in `backend/app/samples/`, so the Lambda package includes them. Regenerate with `.venv/bin/python demo/generate.py`.

## 5. If something goes wrong

| Symptom                                     | Fix                                                                                                                    |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| "Cannot reach the API" on the page          | The backend (terminal 1) isn't running, or `VITE_API_BASE_URL` in `frontend/.env` is wrong. Rebuild after changing it. |
| Blank white page on the workshop machine    | You used the dev server under `/ports/5173/`. Use Option B: build with `--base=./` and run `vite preview`.             |
| "Blocked request. This host is not allowed" | `frontend/vite.config.ts` must allow `.cloudfront.net` (already set on `dev`). Restart the frontend.                   |
| Backend URL shows `{"detail":"Not Found"}`  | Normal for the bare address; the API is under `/api/...`, e.g. `/api/memory`.                                          |
| Memory note didn't change in step 5         | **Remember** wasn't ticked before Dismiss. Tick it and click Dismiss again.                                            |
| An old case appears when the page opens     | It restores your last case. Load a sample to replace it, or stop the backend, delete `local-data/` and restart.        |
| Backend code change not showing             | Restart uvicorn (Ctrl+C, then start it again).                                                                         |