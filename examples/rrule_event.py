import asyncio
from datetime import datetime

from dateutil import rrule

from mango import Agent, AgentAddress, activate, create_ec_container
from mango.util.clock import ExternalClock
from mango.util.distributed_clock import DistributedClockAgent, DistributedClockManager


class Caller(Agent):
    def __init__(self, receiver_addr, recurrency):
        super().__init__()
        self.receiver_addr = receiver_addr
        self.recurrency = recurrency

    def on_ready(self):
        self.schedule_recurrent_task(
            coroutine_func=self.send_hello_world, recurrency=self.recurrency
        )

    async def send_hello_world(self):
        time = datetime.fromtimestamp(self.scheduler.clock.time)
        await asyncio.sleep(0.1)
        await self.send_message(
            receiver_addr=self.receiver_addr,
            content=f"Current time is {time}",
        )

    def handle_message(self, content, meta):
        pass


class Receiver(Agent):
    def __init__(self):
        super().__init__()
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

    c = create_ec_container(addr=addr, clock=clock)
    same_process = False
    c_agents = []
    if same_process:
        
        receiver1 = Receiver()
        c.register(receiver1)
        caller = Caller(receiver1.addr, recurrency)
        c.register(caller)

        receiver2 = Receiver()
        c.register(receiver2)
        caller = Caller(receiver2.addr, recurrency)
        c.register(caller)
        # clock_agent = DistributedClockAgent(c)
        clock_manager = DistributedClockManager(receiver_clock_addresses=[])
        c.register(clock_manager)
    else:
        clock_manager = DistributedClockManager(
            receiver_clock_addresses=[AgentAddress(addr, "clock_agent")]
        )
        c.register(clock_manager)
        # receiver = Receiver(c)
        # caller = Caller(c, addr, receiver.aid, recurrency)
        global receiver
        receiver = None

        def creator(container):
            receiver = Receiver()
            container.register(receiver)
            clock_agent = DistributedClockAgent()
            container.register(clock_agent)

        await c.as_agent_process(agent_creator=creator)
        caller = Caller(receiver.addr, recurrency)
        c.register(caller)
        # await c.as_agent_process(agent_creator=creator)

    if isinstance(clock, ExternalClock):
        async with activate(c):
            for i in range(100):
                await asyncio.sleep(0.01)
                clock.set_time(clock.time + 60)
                next_event = await clock_manager.distribute_time()


if __name__ == "__main__":
    from dateutil.parser import parse

    start = parse("202301010000")
    asyncio.run(main(start))
