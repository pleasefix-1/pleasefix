# Windows onboarding — from a blank machine to a running PleaseFix

Everything runs inside Linux containers, so Windows development is
first-class via WSL2 + Docker — you never install Python, GDAL, or
PostGIS on Windows itself (native Windows GeoDjango is deliberately
unsupported; the GDAL/PROJ toolchain there is a time sink).

Two paths. Path A (Dev Container) is the recommended one-click-ish
route; Path B is the same stack from a plain terminal.

## Step 0 — once per machine (~20 minutes, mostly downloads)

1. **WSL2** — open *PowerShell as Administrator*:

   ```powershell
   wsl --install
   ```

   Reboot when asked. First launch of Ubuntu prompts you to pick a
   Linux username/password.

2. **Docker Desktop** — install from
   <https://www.docker.com/products/docker-desktop/>. In *Settings →
   General* make sure **"Use the WSL 2 based engine"** is on (default),
   and under *Resources → WSL integration* enable your Ubuntu distro.
   (Rancher Desktop works too if Docker Desktop licensing is a concern.)

3. **Clone inside the Linux filesystem** — this matters: bind mounts
   from the Windows filesystem (`C:\...`) are 10–50× slower. Open the
   *Ubuntu* terminal:

   ```sh
   git clone https://github.com/pleasefix-1/pleasefix.git
   cd pleasefix
   cp .env.example .env
   ```

   Line endings are enforced by `.gitattributes` — you do not need to
   configure `core.autocrlf`.

## Path A — VS Code Dev Container (recommended)

1. Install [VS Code](https://code.visualstudio.com/) on Windows with the
   **WSL** and **Dev Containers** extensions.
2. From the Ubuntu terminal, in the repo: `code .`
3. VS Code will offer **"Reopen in Container"** — accept. First build
   takes a few minutes; it starts the whole stack (app, worker,
   PostGIS, Redis, S3, Caddy) and installs the dev toolchain (ruff,
   mypy, pytest) with the right settings pre-wired.
4. Open <http://localhost:8000>. Edit code — the server reloads
   automatically. Run checks in the VS Code terminal:

   ```sh
   uv run pytest
   uv run ruff check .
   uv run mypy .
   ```

## Path B — plain terminal

From the Ubuntu terminal, in the repo:

```sh
docker compose up --build
```

That's the entire stack with live reload (`compose.override.yaml`
bind-mounts your checkout and runs Django's dev server — edits apply
instantly, no rebuild). App: <http://localhost:8000>.

Common commands (all run inside the containers, nothing on Windows):

```sh
docker compose exec app python manage.py createsuperuser
docker compose exec app python manage.py makemigrations
docker compose run --rm app sh -c "uv sync && uv run pytest"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` in Ubuntu | Docker Desktop → Settings → Resources → WSL integration → enable your distro, then restart the terminal |
| Port 8000/80 already in use | Stop the other service, or edit the `ports:` mappings in `compose.yaml` |
| Everything is very slow | Your checkout is on `C:\` (`/mnt/c/...`). Move it into the Linux filesystem (`~/pleasefix`) |
| `exec format error` or `\r: not found` | A file got CRLF line endings past git — `git add --renormalize . && git status`; check your editor isn't overriding `.gitattributes` |
| BM/EN pages show English only | Translations not compiled in your container — `docker compose exec app python manage.py compilemessages` (automatic on normal startup) |
| WSL clock drift after sleep (TLS/apt errors) | `wsl --shutdown` from PowerShell, reopen the terminal |

No Docker at all? You can still build API clients against the hosted
sandbox (planned) with nothing but Node or Python on Windows — see
[CONTRIBUTING](../CONTRIBUTING.md), "Build a client instead".
