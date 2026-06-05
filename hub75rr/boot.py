import json
import os
import time
import machine


def _wifi_connect():
    import network
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return wlan
    wlan.active(True)
    try:
        from config import WIFI_SSID, WIFI_PASSWORD
    except ImportError:
        print("boot: no config.py, skipping OTA")
        return None
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    deadline = time.ticks_add(time.ticks_ms(), 15000)
    while not wlan.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            print("boot: WiFi timeout, skipping OTA")
            return None
        time.sleep(0.2)
    print("boot: WiFi connected:", wlan.ifconfig()[0])
    return wlan


def check_ota():
    try:
        from config import OTA_URL
    except ImportError:
        return

    if _wifi_connect() is None:
        return

    try:
        import urequests
        r = urequests.get(OTA_URL + "/version.json", timeout=8)
        manifest = r.json()
        r.close()
    except Exception as e:
        print("boot: OTA version check failed:", e)
        return

    try:
        with open("_version.json") as f:
            local_ver = json.load(f).get("version")
    except Exception:
        local_ver = None

    if manifest.get("version") == local_ver:
        print("boot: firmware up to date ({})".format(local_ver))
        return

    print("boot: OTA {} -> {}".format(local_ver, manifest.get("version")))
    try:
        import urequests
        for fname in manifest.get("files", []):
            print("boot: fetching", fname)
            r = urequests.get(OTA_URL + "/" + fname, timeout=15)
            tmp = fname + ".tmp"
            with open(tmp, "w") as f:
                f.write(r.text)
            r.close()
            try:
                os.remove(fname)
            except OSError:
                pass
            os.rename(tmp, fname)

        with open("_version.json", "w") as f:
            json.dump(manifest, f)

        print("boot: OTA complete, rebooting")
        time.sleep(1)
        machine.reset()
    except Exception as e:
        print("boot: OTA update failed:", e)


check_ota()
