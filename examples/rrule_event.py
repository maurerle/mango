import asyncio
from datetime import datetime

from dateutil import rrule

from mango import Agent, create_container
from mango.util.clock import ExternalClock
from mango.util.distributed_clock import DistributedClockAgent, DistributedClockManager


class Caller(Agent):
    def __init__(self, container, receiver_addr, receiver_id, recurrency):
        super().__init__(container)
        self.receiver_addr = receiver_addr
        self.receiver_id = receiver_id
        self.schedule_recurrent_task(
            coroutine_func=self.send_hello_world, recurrency=recurrency
        )

    async def send_hello_world(self):
        time = datetime.fromtimestamp(self._scheduler.clock.time)
        await asyncio.sleep(0.1)
        await self.send_acl_message(
            receiver_addr=self.receiver_addr,
            receiver_id=self.receiver_id,
            content=f"Current time is {time}",
            acl_metadata={"sender_id": self.aid},
        )

    def handle_message(self, content, meta):
        pass


class Receiver(Agent):
    def __init__(self, container):
        super().__init__(container)
        self.wait_for_reply = asyncio.Future()

    def handle_message(self, content, meta):
        print(
            f"{self.aid} Received a message with the following content: {content} from {meta['sender_id']}."
        )


async def main(start):
    clock = ExternalClock(start_time=start.timestamp())
    addr = ("127.0.0.1", 5555)
    # market acts every 15 minutes
    recurrency = rrule.rrule(rrule.MINUTELY, interval=15, dtstart=start)

    c = await create_container(addr=addr, clock=clock)
    same_process = False
    c_agents = []
    if same_process:
        receiver = Receiver(c)
        caller = Caller(c, addr, receiver.aid, recurrency)

        receiver2 = Receiver(c)
        caller = Caller(c, addr, receiver2.aid, recurrency)
        # clock_agent = DistributedClockAgent(c)
        clock_manager = DistributedClockManager(c, receiver_clock_addresses=[])
    else:
        clock_manager = DistributedClockManager(c, receiver_clock_addresses=[(addr, "clock_agent")])
        # receiver = Receiver(c)
        # caller = Caller(c, addr, receiver.aid, recurrency)
        global receiver
        receiver = None

        def creator(container):
            receiver = Receiver(container)
            clock_agent = DistributedClockAgent(container)

        await c.as_agent_process(agent_creator=creator)
        caller = Caller(c, addr, receiver.aid, recurrency)
        # await c.as_agent_process(agent_creator=creator)

    if isinstance(clock, ExternalClock):
        for i in range(100):
            await asyncio.sleep(0.01)
            clock.set_time(clock.time + 60)
            next_event = await clock_manager.distribute_time()

    await c.shutdown()


if __name__ == "__main__":
    from dateutil.parser import parse

    start = parse("202301010000")
    asyncio.run(main(start))
