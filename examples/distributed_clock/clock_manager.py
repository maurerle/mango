import asyncio
import logging
from datetime import datetime
from typing import TypedDict

import pandas as pd
from serializer import mango_codec_factory
from tqdm import tqdm

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
from mango.util.distributed_clock import DistributedClockManager
from mango.util.termination_detection import tasks_complete_or_sleeping

logger = logging.getLogger(__name__)


class SimpleBid(TypedDict):
    price: float
    volume: float


class OneSidedMarketRole(Role):
    def __init__(self, demand=1000, receiver_ids=[]):
        super().__init__()
        self.demand = demand
        self.bids = []
        self.receiver_ids = receiver_ids

    def setup(self):
        self.results = []
        self.demands = []

        self.context.subscribe_message(
            self, self.handle_message, lambda content, meta: isinstance(content, dict)
        )

        self.context.subscribe_message(
            self, self.handle_other, lambda content, meta: not isinstance(content, dict)
        )

    def on_ready(self):
        self.context.schedule_periodic_task(coroutine_func=self.clear_market, delay=900)
        self.starttime = self.context.current_timestamp

    async def clear_market(self):
        time = datetime.fromtimestamp(self.context.current_timestamp)
        if self.context.current_timestamp > self.starttime:
            i = time.hour + time.minute / 60
            df = pd.DataFrame.from_dict(self.bids)
            self.bids = []
            price = 0
            if df.empty:
                logger.info("Did not receive any bids!")
            else:
                # simple merit order calculation
                df = df.sort_values("price")
                df["cumsum"] = df["volume"].cumsum()
                filtered = df[df["cumsum"] >= self.demand]
                if filtered.empty:
                    # demand could not be matched
                    price = 100
                else:
                    price = filtered["price"].values[0]
            self.results.append(price)
            self.demands.append(self.demand)
        else:
            logger.info("First opening does not have anything to clear")
            price = 0
        resp = []
        for receiver_addr in self.receiver_ids:
            r = self.context.send_message(
                content={
                    "message": f"Current time is {time}",
                    "price": price,
                    "time": time,
                },
                receiver_addr=receiver_addr,
            )
            resp.append(r)
        for r in resp:
            await r

    def handle_message(self, content, meta):
        # content is SimpleBid
        content["sender_id"] = meta["sender_id"]
        self.bids.append(content)

    def handle_other(self, content, meta):
        # content is other
        print(f'got {content} from {meta.get("sender_id")}')

    async def on_stop(self):
        logger.info(self.results)


async def main(start):
    # connection_type = 'mqtt'
    connection_type = "tcp"

    if connection_type == "mqtt":
        addr = "c1"
        other_container_addr = "c2"
        create_container = create_mqtt_container
        container_kwargs = {
            "client_id": "container_2",
            "broker_addr": ("localhost", 1883, 60),
            "mqtt_kwargs": {
                "transport": "tcp",
            },
        }
    else:
        addr = ("localhost", 5555)
        other_container_addr = ("localhost", 5556)
        create_container = create_tcp_container
        container_kwargs = {}

    clock = ExternalClock(start_time=start.timestamp())
    c = create_container(addr, codec=mango_codec_factory(), clock=clock, **container_kwargs)
    clock_agent = DistributedClockManager(
        receiver_clock_addresses=[AgentAddress(other_container_addr, "clock_agent")]
    )
    c.register(clock_agent)

    market = RoleAgent()
    receiver_ids = [AgentAddress(other_container_addr, "a0"), AgentAddress(other_container_addr, "a1")]
    market.add_role(OneSidedMarketRole(demand=1000, receiver_ids=receiver_ids))
    c.register(market, suggested_aid="market")

    async with activate(c):
        # distribute time here, so that containers already have correct start time
        next_event = await clock_agent.distribute_time()

        if isinstance(clock, ExternalClock):
            for i in tqdm(range(30)):
                next_event = await clock_agent.distribute_time()
                logger.info("current step: %s", clock.time)
                await tasks_complete_or_sleeping(c)
                # comment next line to see that the first message is not received in correct timings
                # also comment sleep(0) in termination_detection to see other timing problems
                next_event = await clock_agent.distribute_time()
                clock.set_time(next_event)


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    start = datetime(2023, 1, 1)
    asyncio.run(main(start))
