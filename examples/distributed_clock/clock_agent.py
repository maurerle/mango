import asyncio
import logging
from typing import TypedDict

import numpy as np
from serializer import mango_codec_factory

from mango import (
    AgentAddress,
    Role,
    RoleAgent,
    activate,
    create_mqtt_container,
    create_tcp_container,
)
from mango.messages.message import Performatives
from mango.util.clock import ExternalClock
from mango.util.distributed_clock import DistributedClockAgent

logger = logging.getLogger(__name__)


class SimpleBid(TypedDict):
    price: float
    volume: float


class BiddingRole(Role):
    def __init__(self, receiver_addr: AgentAddress, volume=100, price=0.05):
        super().__init__()
        self.receiver_addr = receiver_addr
        self.volume = volume
        self.price = price

    def setup(self):
        self.volume = self.volume
        self.price = self.price
        self.context.subscribe_message(
            self, self.handle_message, lambda content, meta: True
        )
        self.context.schedule_periodic_task(coroutine_func=self.say_hello, delay=1200)

    async def say_hello(self):
        await self.context.send_message(
            content="Hello Market",
            receiver_addr=self.receiver_addr,
        )

    def handle_message(self, content, meta):
        print("handle message", content)
        t = content["time"]
        print("scheduled task", self.context.scheduler.clock.time)
        self.context.schedule_instant_task(coroutine=self.set_bids())
        logger.debug("current_time %s", self.context.current_timestamp)

    async def set_bids(self):
        # await asyncio.sleep(1)
        price = self.price + 0.01 * self.price * np.random.random()
        logger.debug("did set bids at %s", self.context.scheduler.clock.time)

        await self.context.send_message(
            content={"price": price, "volume": self.volume},
            receiver_addr=self.receiver_addr,
        )


async def main():
    # connection_type = 'mqtt'
    connection_type = "tcp"

    if connection_type == "mqtt":
        addr = "c2"
        other_container_addr = "c1"
        create_container = create_mqtt_container
        container_kwargs = {
            "client_id": "container_2",
            "broker_addr": ("localhost", 1883, 60),
            "mqtt_kwargs": {
                "transport": "tcp",
            },
        }
    else:
        addr = ("localhost", 5556)
        other_container_addr = ("localhost", 5555)
        create_container = create_tcp_container
        container_kwargs = {}

    c = create_container(addr, codec=mango_codec_factory(), clock=ExternalClock(start_time=0), **container_kwargs)

    clock_agent = DistributedClockAgent()
    c.register(clock_agent, "clock_agent")
    receiver_addr = AgentAddress(other_container_addr, "market")

    for i in range(2):
        agent = RoleAgent()
        c.register(agent, suggested_aid=f"a{i}")
        agent.add_role(
            BiddingRole(receiver_addr, price=0.05 * (i % 9))
        )

    try:
        async with activate(c):
            await clock_agent.stopped
    except Exception as e:
        print(e)


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    asyncio.run(main())
