# papyrus

> a simple RSS feed aggregator that learns what you like to read

RSS feeds are great, but they can also be a firehose.
What if we could recommend articles based on what *you* like? 

Papyrus uses a super-simple recommendation system (SVM over TF-IDF features) to learn your preferences.

![papyrus](figures/papyrus.png)

### Setup

- Requires python3 and node.js
- Pick a port for the frontend and backend
  - Default: `2400` for frontend, `2430` for backend
- Configure `.env`, `server/Makefile`, and `start.sh` accordingly
  - I will probably make this easier in the future
```bash
# .env
VITE_FRONTEND_PORT=<YOUR_FRONTEND_PORT>
VITE_BACKEND_URL=http://localhost:<YOUR_BACKEND_PORT>/api
```

```Makefile
# server/Makefile
dev:
	uvicorn app:app --reload --host 0.0.0.0 --port <YOUR_BACKEND_PORT>

prod:
	uvicorn app:app --host 0.0.0.0 --port <YOUR_BACKEND_PORT>
```

```bash
# start.sh
yarn preview --port <YOUR_FRONTEND_PORT> &
```

Then run `./start.sh` in the background (either tmux or append `&`)

The database lives in `server/data`, in case you want to back it up. I use an NGINX reverse proxy to serve the frontend/backend + add password protection.

### Disclaimers/Notes

1. This was hacked together in my spare time over ~1 week
2. A lot of this code is underoptimized; I'm working on making page requests faster
3. A lot of this code is LLM generated. I want to see how far I can push current tools.
4. The style is the same as my [blog](https://tanaybiradar.com/) - derived from [bearblog](https://bearblog.dev/) and [flexoki](https://stephango.com/flexoki)
