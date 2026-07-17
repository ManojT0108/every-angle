# Every Angle web app

React + TypeScript + Vite frontend for the Every Angle FastAPI backend.

Start the backend from the repository root:

```bash
./.venv/bin/uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```bash
cd web
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` and `/media` to the backend on port 8000.

Checks:

```bash
npm run lint
npm run build
npm test
```

Unit tests use Vitest, the Vite-native test runner installed as a development dependency.
