# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Services

| Service | Source | Role |
|---|---|---|
| switchrr | submodule `./switchrr` | ZMQ routing daemon — forwards frames from active mode to Indicatrr, routes hardware events back |
| boardrr | submodule `./boardrr` | UK train departure display mode (256×64 OLED) |
| powrr | submodule `./powrr` | Solar power monitoring display mode (MQTT/Home Assistant) |
| issrr | submodule `./issrr` | ISS real-time tracker display mode — orbit, crew, docking, space weather, events, passes |
| tiderr | submodule `./tiderr` | Tide times display mode — graph, tidal character, moon/sun, marine conditions (toggle 4) |
| webrr | local `./webrr` | FastAPI/WebSocket browser tap — serves a live view of the active frame over HTTP (port 8888) |

## Stack commands

```bash
# First-time setup
git clone --recurse-submodules https://github.com/nimarchetti/displayrr.git
cd displayrr
cp .env.sample .env   # fill in credentials and IPs

# Start / stop
docker compose up -d
docker compose down

# Rebuild a single service after code changes
docker compose up -d --build <service>

# Follow logs for one service
docker compose logs -f <service>
```

## Architecture

External **Indicatrr** Pi Zero drives the physical OLED and rotary encoder hardware. It connects to **switchrr** (the only service with a published host port, `5556`) and pushes rendered-frame requests and hardware events. All inter-container communication uses the `displayrr` bridge network with service names as hostnames.

### ZMQ port layout (all on the `displayrr` network)

| Port | Direction | Purpose |
|---|---|---|
| 5556 | published to host | Indicatrr → switchrr hardware events (PUSH/PULL) |
| 5557 | internal | switchrr → mode containers event broadcast (PUB/SUB) |
| 5600–5603 | internal | mode container → switchrr frame channels (PUSH/PULL, one per toggle position) |
| 5650 | internal | switchrr → webrr frame tap (PUB/SUB) |

### Mode container contract

Each mode container must:
- Connect a ZMQ `PUSH` socket to `SWITCHRR_FRAME_ADDRESS` (e.g. `tcp://switchrr:5600`) and push raw 256×64 frame bytes
- Subscribe a ZMQ `SUB` socket to `SWITCHRR_EVENT_ADDRESS` (`tcp://switchrr:5557`) to receive `MODE_ACTIVE` / `MODE_INACTIVE` / `ENCODER_DELTA` / `ENCODER_PUSH` events
- Set `MODE_NAME` env var to match its `mode_name` in `MODE_REGISTRY`

See `switchrr/docs/switchrr-spec.md` for the full wire protocol.

### MODE_REGISTRY

Defined as a JSON array in `.env`. Each entry maps a toggle switch position (1–4) to a mode container. The entry with `"default": true` is active at startup. `frame_bind_address` is the address switchrr binds to receive that mode's frames.

## Adding a new mode container

1. Develop the new mode as its own repo and push to GitHub
2. `git submodule add https://github.com/nimarchetti/<newmode>.git <newmode>`
3. Add a service block to `docker-compose.yml` — set `SWITCHRR_FRAME_ADDRESS` and `SWITCHRR_EVENT_ADDRESS` in the `environment:` block using service name `switchrr`
4. Add any new env vars to `.env` and `.env.sample`
5. Add an entry to `MODE_REGISTRY` in `.env` (next available `toggle_position` 1–4)
6. Commit `.gitmodules`, the submodule directory pointer, and `docker-compose.yml`

## Updating a submodule to latest

```bash
cd <submodule> && git pull origin main && cd ..
git add <submodule>
git commit -m "chore: update <submodule> to latest"
```
