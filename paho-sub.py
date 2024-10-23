# python 3.11

import logging
import random
import time

import paho.mqtt.client as paho

logging.basicConfig(format="%(asctime)s;%(levelname)s;%(message)s")

logger = logging.getLogger(__name__)

broker = "localhost"
port = 1883
topic = "python/mqtt"
# Generate a Client ID with the publish prefix.
client_id = f"publish-{random.randint(0, 1000)}"
# username = 'emqx'
# password = 'public'


def connect_mqtt():
    def on_connect(client, userdata, flags, rc, pa):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)

    def on_message(client, userdata, message):
        logger.warning("got message %s", message)

    client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id)
    # client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port)
    client.subscribe(topic)

    return client


def publish(client):
    msg_count = 1
    while True:
        # time.sleep(1)
        msg = f"messages: {msg_count}"
        result = client.publish(topic, msg)
        # result: [0, 1]
        status = result[0]
        if status == 0:
            print(f"Send `{msg}` to topic `{topic}`")
        else:
            print(f"Failed to send message to topic {topic}")
        msg_count += 1
        if msg_count > 5:
            break


def run():
    client = connect_mqtt()
    client.loop_start()
    time.sleep(10)
    # publish(client)
    client.loop_stop()


if __name__ == "__main__":
    run()
