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
        await self.send_acl_message(
            receiver_addr=self.receiver_addr,
            receiver_id=self.receiver_id,
            content=f"Current time is {time}",
        )

    def handle_message(self, content, meta):
        pass


class Receiver(Agent):
    def __init__(self, container):
        super().__init__(container)
        self.wait_for_reply = asyncio.Future()

    def handle_message(self, content, meta):
        print(f"Received a message with the following content: {content}.")


async def main(start):
    clock = ExternalClock(start_time=start.timestamp())
    addr = ("127.0.0.1", 5555)
    # market acts every 15 minutes
    recurrency = rrule.rrule(rrule.MINUTELY, interval=15, dtstart=start)

    c = await create_container(addr=addr, clock=clock)
    same_process = True

    clock_manager = DistributedClockManager(c, receiver_clock_addresses=[addr])

    if same_process:
        receiver = Receiver(c)
        caller = Caller(c, addr, receiver.aid, recurrency)
        clock_agent = DistributedClockAgent(c)
    else:

        def creator(container):
            receiver = Receiver(container)
            caller = Caller(container, addr, receiver.aid, recurrency)
            clock_agent = DistributedClockAgent(container)

        await c.as_agent_process(agent_creator=creator)
    if isinstance(clock, ExternalClock):
        for i in range(100):
            await asyncio.sleep(0.01)
            clock.set_time(clock.time + 60)
            await clock_manager.distribute_time()
    await c.shutdown()


if __name__ == "__main__":
    from dateutil.parser import parse

    start = parse("202301010000")
    asyncio.run(main(start))
