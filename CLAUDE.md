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

One or more external **Indicatrr** Pi Zeros each drive a physical OLED and input hardware. Each Indicatrr connects to **switchrr** on its display's `events_bind_port` (default `5556`, published to the host). All inter-container communication uses the `displayrr` bridge network with service names as hostnames.

### ZMQ port layout (all on the `displayrr` network)

| Port | Direction | Purpose |
|---|---|---|
| 5556 | published to host | Indicatrr → switchrr hardware events, per display (PUSH/PULL) |
| 5557 | internal | switchrr → mode containers event broadcast (PUB/SUB) |
| 5600–5603 | internal | mode container PUB frame source; switchrr SUB-connects (PUB/SUB) |
| 5650 | internal | switchrr → webrr frame tap (PUB/SUB, legacy 2-part format) |

### Frame wire format

Mode containers publish 4-part multipart frames:

```
[mode_name (bytes), width (bytes), height (bytes), pixel_data (bytes)]
```

switchrr routes frames to displays where `active_mode == mode_name` and `(width, height)` matches the display's configured dimensions. It converts to a legacy 2-part `[header_json, pixels]` format before forwarding to Indicatrr (keeping Indicatrr unchanged).

### Mode container contract

Each mode container must:
- Bind a ZMQ `PUB` socket to `SWITCHRR_FRAME_BIND_ADDRESS` (e.g. `tcp://0.0.0.0:5600`) and publish 4-part frames
- Subscribe a ZMQ `SUB` socket to `SWITCHRR_EVENT_ADDRESS` (`tcp://switchrr:5557`) to receive `MODE_ACTIVE` / `MODE_INACTIVE` / `ENCODER_DELTA` / `ENCODER_PUSH` events
- Set `MODE_NAME` env var to match its `mode_name` entry in `DISPLAY_REGISTRY`
- Optionally read `DISPLAY_REGISTRY` to discover which `(width, height)` combinations to render — see `_parse_display_sizes()` in existing mode containers

### DISPLAY_REGISTRY

Defined as a JSON array in `.env`. Each entry describes one physical display: its dimensions, Indicatrr address, hardware-event port, and the list of modes available on it. The mode entry with `"default": true` is activated on startup. `frame_pub_address` is the address switchrr SUB-connects to for that mode's frames (uses Docker service name within the stack).

```json
[{
  "display_id": "default",
  "width": 256, "height": 64,
  "indicatrr_address": "tcp://<ip>:5555",
  "events_bind_port": 5556,
  "modes": [
    {"mode_name": "uk_tdd", "display_name": "Train Departures",
     "frame_pub_address": "tcp://boardrr:5600", "default": true},
    {"mode_name": "tiderr", "display_name": "Tides",
     "frame_pub_address": "tcp://tiderr:5603"}
  ]
}]
```

switchrr falls back to the legacy `MODE_REGISTRY` + `INDICATRR_FRAME_ADDRESS` + `HARDWARE_EVENTS_BIND_ADDRESS` vars if `DISPLAY_REGISTRY` is not set.

## Adding a new mode container

1. Develop the new mode as its own repo and push to GitHub (or use `/scaffold`)
2. `git submodule add https://github.com/nimarchetti/<newmode>.git <newmode>`
3. Add a service block to `docker-compose.yml` — set `SWITCHRR_FRAME_BIND_ADDRESS: tcp://0.0.0.0:<port>` and `SWITCHRR_EVENT_ADDRESS: tcp://switchrr:5557`
4. Add any new env vars to `.env` and `.env.sample`
5. Add a mode entry to the relevant display in `DISPLAY_REGISTRY` in `.env`, with `frame_pub_address: tcp://<service>:<port>`
6. Commit `.gitmodules`, the submodule directory pointer, and `docker-compose.yml`

## Updating a submodule to latest

```bash
cd <submodule> && git pull origin main && cd ..
git add <submodule>
git commit -m "chore: update <submodule> to latest"
```
