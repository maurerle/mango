# python 3.11-3.13
"""
This script was used to debug a weird behavior in paho.mqtt.python
See https://github.com/eclipse-paho/paho.mqtt.python/issues/874

This script works fine with WAIT_FOR_PUBLISH either True or False and with
myQOS = 0 or 1.
Having myQOS set to 1 has a delay of 40ms per call, if TCP_NODELAY is not set on the MQTT broker.
This can be set through the `set_tcp_nodelay=true` config in mosquitto.conf

See paho-sub.py for an implementation of similar behavior which somehow deadlocks.
"""
import logging
import random
from multiprocessing.pool import ThreadPool

import paho.mqtt.client as paho

logger = logging.getLogger(__name__)

WAIT_FOR_PUBLISH = True
myQOS = 0
broker = "localhost"
port = 1883
topic = "python/mqtt"
# Generate a Client ID with the publish prefix.
client_id = f"publish-{random.randint(0, 1000)}"

pool = ThreadPool(processes=4)

def connect_mqtt(topic):
    def on_connect(client, userdata, flags, rc, pa):
        if rc == 0:
            logger.info("Connected to MQTT Broker!")
        else:
            logger.error("Failed to connect, return code %d\n", rc)
        
    def thread_publish(client, topic, payload: int):
        number = int(payload) + 1
        if number < 100:
            info = client.publish(topic, number, qos=myQOS)
            logger.info("did send message %s", number)
        # wait for publish does deadlock here
        if WAIT_FOR_PUBLISH:
            info.wait_for_publish()

    def on_message(client, userdata, message: paho.MQTTMessage):
        logger.info("got message %s", message.payload)
        
        payload = message.payload
        # using a threadpool here did not help either
        # pool.apply(thread_publish, args=(client, topic, message.payload))
        number = int(payload) + 1
        if number < 100:
            info = client.publish(topic, number, qos=myQOS)
            # wait for publish does deadlock here
            #info.wait_for_publish()
            logger.info("did send message %s", number)

    client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port)
    client.subscribe(topic, qos=myQOS)

    return client


def run():
    client = connect_mqtt(topic)
    client.loop_start()

    result = client.publish(topic, 1, qos=myQOS)
    result.wait_for_publish()

    # this helps when QoS is 0 to wait until all is received
    import time
    time.sleep(1)

    client.loop_stop()


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s;%(levelname)s;%(message)s", level="INFO")
    run()
