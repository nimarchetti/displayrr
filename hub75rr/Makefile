PORT ?= /dev/ttyACM0

.PHONY: deploy test-display

deploy:
	mpremote connect $(PORT) \
		cp serial_client.py :serial_client.py + \
		cp main.py          :main.py          + \
		cp config.py        :config.py        + \
		reset

test-display:
	mpremote connect $(PORT) run test_display.py
