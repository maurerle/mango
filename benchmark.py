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

import pandas as pd

from mango import (
    Agent,
    activate,
    addr,
    create_mqtt_container,
    create_tcp_container,
    sender_addr,
)
from mango.util.clock import ExternalClock
from mango.util.distributed_clock import DistributedClockAgent, DistributedClockManager
from mango.util.termination_detection import tasks_complete_or_sleeping

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

async def func(func_type, connection_type, transport, max_count):
    init_addr = ("127.0.0.1", 1555) if connection_type == "tcp" else "c1"
    repl_addr = ("127.0.0.1", 1556) if connection_type == "tcp" else "c2"

    clock_man = ExternalClock(5)
    clock_ag = ExternalClock()

    if transport == "websockets":
        broker = ("127.0.0.1", 9005, 60)
    elif transport == "tcp":
        broker = ("127.0.0.1", 1884, 60)
    elif transport == "unix":
        broker = ("/tmp/mqtt.sock")
    else:
        raise ValueError(f"Unknown transport {transport}")

    if connection_type == "tcp":
        container_man = create_tcp_container(
            addr=init_addr,
            clock=clock_man,
        )
        container_ag = create_tcp_container(
            addr=repl_addr,
            clock=clock_ag,
        )
    else:
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
            schedule_timestamp=func_type == "timestamp"
        )
    )

    if func_type == "timestamp":
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
    else:
        async with activate(container_man, container_ag) as c:
            container_man.clock.set_time(container_man.clock.time + 5)

            # we do not have distributed termination detection yet in core
            assert caller.i < caller.max_count
            await caller.done
    assert caller.i == caller.max_count


if __name__ == "__main__":
    #logging.getLogger("mango").setLevel(logging.INFO)
    logging.basicConfig(format="%(asctime)s;%(levelname)s;%(message)s")
    connection_type = "mqtt"
    max_count = 8000
    EXEC_RUNTIME_STUDY = False

    if EXEC_RUNTIME_STUDY:
        results = []
        for func_type in ["ping_pong","timestamp"]:
            for connection_type in ["mqtt", "tcp"]:
                for transport in ["tcp", "websockets", "unix"]:
                    if connection_type == "tcp" and transport != "tcp":
                        continue

                    for max_count in [
                        1,
                        2,
                        25,
                        50,
                        100,
                        200,
                        300,
                        400,
                        500,
                        600,
                        700,
                        800,
                        900,
                        1000,
                        #5000,
                        #10000,
                    ]:
                        t = time.time()
                        asyncio.run(func(func_type, connection_type, transport=transport, max_count=max_count))
                        duration = time.time() - t
                        rtt = f"{duration/max_count*1000:.2f} ms"
                        print("\t".join([func_type, connection_type, transport, str(max_count), str(duration), rtt]))
                        results.append(
                            [func_type, connection_type, transport, max_count, duration]
                        )
        
        df = pd.DataFrame(results, columns=["function", "connection_type", "transport", "count", "duration"])
        df["roundtrip_per_second"] = df["count"] / df["duration"]
        print(df)
        df.to_csv("runtime.csv", index=None)

    SAVE_FIG = True

    if SAVE_FIG:
        import matplotlib.pyplot as plt
        df = pd.read_csv("runtime.csv")
        pivot_df = df.pivot(columns=["function", "connection_type", "transport"], index="count")
        # substract duration with 1 message (shows overhead)
        startup_duration = pivot_df["duration"].loc[1]
        print(startup_duration)
        diff = pivot_df["duration"] - pivot_df["duration"].loc[1]
        # recalculate roundtrip per second
        inverse_df = 1 / diff.div(diff.index.values, axis=0)
        inverse_df =inverse_df.clip(0)
        pivot_df["roundtrip_per_second"] = inverse_df
        # remove index=1 which is infinity
        pivot_df = pivot_df.drop(1)
        df[df.connection_type == "mqtt"]
        pivot_df["roundtrip_per_second"][pivot_df.index <= 1000].plot(
            figsize=(10, 5), grid=True
        )
        plt.ylabel("roundtrips per second")
        plt.title("roundtrips by technology and method")
        plt.savefig("roundtrip_per_seconds.svg")

        pivot_df["duration"].plot(figsize=(10, 5), grid=True)
        plt.savefig("duration.svg")