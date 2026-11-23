"""MQTT broker that lives inside this project (no global install needed).

A small pure-Python broker (amqtt, installed in .venv by `pipenv install`).
Good for development and small setups; for many devices in production a
dedicated broker such as Mosquitto is the better choice (see README.md).

Who may connect and what they may do:
  * Each ESP32 logs in with its device ID + secret (checked against devices.json).
    It may only PUBLISH to   devices/<its id>/data  and  devices/<its id>/status
    and only SUBSCRIBE to    devices/<its id>/cmd
  * server.py logs in as "server" and may do everything.
  * Anyone else is refused.

Run:  python src/mqtt/mqtt.py            (this computer only)
      python src/mqtt/mqtt.py --lan      (devices on your Wi-Fi can connect)
"""

import argparse
import asyncio
import hmac
import logging

from amqtt.broker import Broker
from amqtt.contexts import Action
from amqtt.plugins.base import BaseAuthPlugin, BaseTopicPlugin

import config
import store


class DeviceAuthPlugin(BaseAuthPlugin):
    """Password check: devices against devices.json, the server against its secret file."""

    async def authenticate(self, *, session):
        user, password = session.username, session.password
        if not user or not password:
            return False
        if session.client_id != user:   # a device may not borrow another client's ID
            return False

        if user == store.SERVER_USER:
            return hmac.compare_digest(password, store.server_secret())
        return store.verify_device(user, password)


class DeviceTopicPlugin(BaseTopicPlugin):
    """A device may only touch its own topics."""

    async def topic_filtering(self, *, session=None, topic=None, action=None):
        if session is None or not topic:
            return False
        user = session.username
        if user == store.SERVER_USER:
            return True

        base = "devices/%s/" % user
        if action == Action.PUBLISH:
            return topic in (base + "data", base + "status")
        if action in (Action.SUBSCRIBE, Action.RECEIVE):
            return topic == base + "cmd"
        return False


async def run(bind, port):
    broker = Broker(
        {
            "listeners": {"default": {"type": "tcp", "bind": "%s:%d" % (bind, port)}},
            # Loaded by name: this file is imported again as the module "mqtt"
            "plugins": {
                "mqtt.DeviceAuthPlugin": {},
                "mqtt.DeviceTopicPlugin": {},
            },
        }
    )
    await broker.start()
    print("MQTT broker running on %s:%d   (Ctrl + C to stop)" % (bind, port))
    try:
        await asyncio.Event().wait()  # run until Ctrl + C
    finally:
        await broker.shutdown()
        print("Broker stopped.")


def main():
    parser = argparse.ArgumentParser(description="Project MQTT broker")
    parser.add_argument("--lan", action="store_true",
                        help="listen on all network interfaces (default: this computer only)")
    parser.add_argument("--port", type=int, default=config.BROKER_PORT, help="broker port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.ERROR)
    bind = "0.0.0.0" if args.lan else "127.0.0.1"
    if args.lan:
        print("Listening on your network: %s:%d  (devices must log in with their secret)"
              % (config.lan_ip(), args.port))

    try:
        asyncio.run(run(bind, args.port))
    except KeyboardInterrupt:
        pass
    except OSError as error:
        print("Cannot start the broker:", error)
        print("Is another broker already using port %d?" % args.port)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
