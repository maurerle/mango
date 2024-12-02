"""
This is a special case extracted as a single script from phd.py

It shows a simulation of two ping pong agents, which react based on a constantly progressing time.
The clock runs distributed through the DistributedClockManager and is set coherently on both mango containers.

This has round trip times of more than 40ms if TCP_NODELAY is not set on the MQTT broker.
Similar to how QoS=1 behaves (see paho-sub.py and paho-test.py)
This can be set through the `set_tcp_nodelay=true` config in mosquitto.conf

Independent of the selected transport, TCP, websockets or unis sockets, the round trip times are slightly below 1 ms.
"""
import asyncio
import logging
import time

from mango import Agent, activate, addr, create_mqtt_container, sender_addr
from mango.util.clock import ExternalClock
from mango.util.distributed_clock import DistributedClockAgent, DistributedClockManager
from mango.util.termination_detection import tasks_complete_or_sleeping

#logging.getLogger("mango").setLevel(logging.INFO)
logging.basicConfig(format="%(asctime)s;%(levelname)s;%(message)s")
connection_type = "mqtt"
max_count = 8000

transport = "unix"
if transport == "websockets":
    broker = ("127.0.0.1", 9005, 60)
elif transport == "tcp":
    broker = ("127.0.0.1", 1884, 60)
elif transport == "unix":
    broker = ("/tmp/mqtt.sock")
else:
    raise ValueError(f"Unknown transport {transport}")

QOS =0

class Caller(Agent):
    def __init__(
        self,
        receiver_addr,
        send_response_messages=False,
        max_count=100,
        schedule_timestamp=False,
    ):
        super().__init__()
        self.i = 0
        self.send_response_messages = send_response_messages
        self.max_count = max_count
        self.schedule_timestamp = schedule_timestamp
        self.done = asyncio.Future()
        self.target = receiver_addr

    def on_ready(self):
        self.schedule_timestamp_task(
            coroutine=self.send_hello_world(self.target),
            timestamp=self.current_timestamp + 5,
        )

    async def send_hello_world(self, receiver_addr):
        await self.send_message(receiver_addr=receiver_addr, content="Hello World", qos=QOS)

    async def send_ordered(self, meta):
        await self.send_message(
            content=self.i,
            receiver_addr=sender_addr(meta), qos=QOS
        )

    def handle_message(self, content, meta):
        self.i += 1
        if self.i < self.max_count and self.send_response_messages:
            if self.schedule_timestamp:
                self.schedule_timestamp_task(
                    self.send_ordered(meta), self.current_timestamp + 5
                )
            else:
                self.schedule_instant_task(self.send_ordered(meta))
        elif not self.done.done():
            self.done.set_result(True)


class Receiver(Agent):
    def handle_message(self, content, meta):
        self.schedule_instant_message(
            receiver_addr=sender_addr(meta),
            content=content,
        )

async def func(connection_type, max_count):
    init_addr = "c1"
    repl_addr = "c2"

    clock_man = ExternalClock(5)
    clock_ag = ExternalClock()

    container_man = create_mqtt_container(
        broker_addr=broker,
        client_id="container_1",
        clock=clock_man,
        inbox_topic=init_addr,
        transport=transport,
    )
    container_ag = create_mqtt_container(
        broker_addr=broker,
        client_id="container_2",
        clock=clock_ag,
        inbox_topic=repl_addr,
        transport=transport,
    )

    clock_agent = container_ag.register(DistributedClockAgent())
    clock_manager = container_man.register(
        DistributedClockManager(
            receiver_clock_addresses=[addr(repl_addr, clock_agent.aid)]
        )
    )
    receiver = container_ag.register(Receiver())
    caller = container_man.register(
        Caller(
            addr(repl_addr, receiver.aid),
            send_response_messages=True,
            max_count=max_count,
            schedule_timestamp=True
        )
    )

    # we do not have distributed termination detection yet in core
    async with activate(container_man, container_ag) as cl:
        assert caller.i < caller.max_count

        import time

        tt = 0
        if isinstance(container_man.clock, ExternalClock):
            for i in range(caller.max_count):
                await tasks_complete_or_sleeping(container_man)
                t = time.time()
                await clock_manager.send_current_time()
                next_event = await clock_manager.get_next_event()
                #next_event = clock_manager.scheduler.clock.time
                tt += time.time() - t

                container_man.clock.set_time(next_event)

        await caller.done

    assert caller.i == caller.max_count

t = time.time()
asyncio.run(func(connection_type, max_count=max_count))
duration = time.time() - t
print("total duration", duration)
print(f"roundtrip time {duration/max_count*1000:.2f} ms")