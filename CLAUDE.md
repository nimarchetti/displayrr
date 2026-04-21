# displayrr

Parent stack repo for the Raspberry Pi display system. Brings up all display services as a single Docker Compose stack.

## Services

| Service | Submodule | Role |
| --- | --- | --- |
| switchrr | `./switchrr` | ZMQ routing daemon — forwards frames from active mode to Indicatrr, routes hardware events back |
| boardrr | `./boardrr` | UK train departure display mode (256×64 OLED) |
| powrr | `./powrr` | Solar power monitoring display mode (MQTT/Home Assistant) |

## Stack setup

```bash
git clone --recurse-submodules https://github.com/nimarchetti/displayrr.git
cd displayrr
cp .env.sample .env   # fill in credentials and IPs
docker compose up -d
```

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
git commit -m "Update <submodule> to latest"
```

## Architecture

External Indicatrr Pi Zero (`10.0.1.196`) drives the physical OLED and rotary encoder hardware. It pushes rendered-frame requests and hardware events to this host via ZMQ. switchrr is the only service with a published port (`5556`) for that external connection. All inter-container communication uses the `displayrr` bridge network with service names as hostnames.

See `switchrr/docs/switchrr-spec.md` and `boardrr/docs/` for protocol details.
