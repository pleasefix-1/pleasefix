# Bootstrap for developing OUTSIDE the dev container / compose image
# (running `uv run manage.py …` / pytest directly on the host).
# The Dockerfile installs the same system packages for the image; CI
# runs `make system-deps` so the package list lives in one place.
#
#   make bootstrap     # apt packages + .env + uv sync + compiled BM messages
#   make system-deps   # just the apt packages

# GeoDjango needs GDAL/GEOS (binutils for its library discovery);
# manage.py {make,compile}messages need GNU gettext.
# Keep in sync with the Dockerfile's apt-get install line.
SYSTEM_PACKAGES := binutils gdal-bin libgdal-dev gettext

# Root shells (servers, containers) run apt directly; everyone else via sudo.
SUDO := $(shell [ "$$(id -u)" = 0 ] || echo sudo)

.PHONY: bootstrap system-deps

bootstrap: system-deps
	test -f .env || cp .env.example .env
	uv sync
	uv run python manage.py compilemessages

system-deps:
	@command -v apt-get >/dev/null || { \
	  echo "apt-get not found — this target is for Debian/Ubuntu."; \
	  echo "macOS: brew install gdal gettext (see README + .env.example)."; \
	  exit 1; }
	$(SUDO) apt-get update
	$(SUDO) apt-get install -y --no-install-recommends $(SYSTEM_PACKAGES)
