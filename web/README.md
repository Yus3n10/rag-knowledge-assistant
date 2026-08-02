# web

React + TypeScript frontend for the OSHA RAG assistant. Talks to the FastAPI
backend in `../api` via `/api` (proxied to `http://localhost:8000` in dev,
see `vite.config.ts`).

## Dev

```
npm install
npm run dev
```

## Test

```
npm test
```

`src/fixtures/*.json` are raw `POST /ask` responses captured against the
running API, used so component tests don't need a live backend.
