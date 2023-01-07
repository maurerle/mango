import asyncio
from mango import RoleAgent, Agent, create_container, Role
from mango.util.clock import ExternalClock
from mango.messages.message import Performatives
from datetime import datetime, timedelta
from dateutil import rrule
import pandas as pd
import numpy as np
import logging
import time
from dateutil.parser import parse
from dataclasses import dataclass

logger = logging.getLogger(__name__)

'''
This snippet describes a TwoSidedMarketRole which makes a Merit-Order for Demand and Generation
and the BiddingRole which sends a bid for one quarter hour to this market,
just like in the previous twosid_market.py example.

Additionally, Intermediary markets are created which bid their difference to the upper market after clearing their local energy market.

Each IntermediaryMarketAgent uses both Roles (TwoSidedMarketRole and BiddingAgent).
'''

@dataclass
class SimpleBid:
    price: float
    volume: float


class TwoSidedMarketRole(Role):
    def __init__(self, start: datetime):
        super().__init__()
        self.bids = []
        self.start = start

    def setup(self):
        self.context.results = []
        self.context.demands = []
        self.context.receiver_ids = []

        def list_condition(content, meta):
            return isinstance(content, list) and all([type(e)==SimpleBid for e in content])

        self.context.subscribe_message(
            self, self.handle_message, lambda content, meta: isinstance(content, SimpleBid))
        self.context.subscribe_message(
            self, self.handle_list_message, list_condition)

        # market acts every 15 minutes
        recurrency = rrule.rrule(rrule.MINUTELY, interval=15, dtstart=start)
        self.context.schedule_recurrent_task(coroutine_func=self.clear_market, recurrency=recurrency)

    async def clear_market(self):
        time = datetime.fromtimestamp(self.context.current_timestamp)
        i = time.hour + time.minute/60
        df = pd.DataFrame.from_dict(self.bids)
        self.bids = []
        price = 0
        demand = 0
        if not df.empty:
            # simple merit order calculation
            # generation
            asks = df[df['volume']>0].sort_values('price')
            # demand
            bids = df[df['volume']<0].sort_values('price', ascending=False)
            asks['cumsum'] = asks['volume'].cumsum()
            bids['cumsum'] = bids['volume'].cumsum()
            for i in range(len(bids['cumsum'])):
                vol = bids.iloc[i]['cumsum']
                # get first price to match demand (vol)
                generation = asks[asks['cumsum'] >= -vol]['price']
                if not generation.empty:
                    gen_price = generation.values[0]
                    # check if generation price is below highest price demand is willing to pay
                    # for production of vol
                    if gen_price <= bids.iloc[i]['price']:
                        price = gen_price
                        demand = vol
                    else:
                        break

            dem = bids['cumsum'].values[-1]
            gen = asks['cumsum'].values[-1]
            self.context.volume = dem + gen
        self.context.price = price
        self.context.results.append(price)
        self.context.demands.append(demand)
        acl_metadata = {
            'performative': Performatives.inform,
            'sender_id': self.context.aid,
            'sender_addr': self.context.addr,
            'conversation_id': 'conversation01'
        }
        resp = []
        for receiver_addr, receiver_id in self.context.receiver_ids:
            r = self.context.send_acl_message(receiver_addr=receiver_addr,
                                              receiver_id=receiver_id,
                                              acl_metadata=acl_metadata,
                                              content={'message': f'Current time is {time}',
                                                       #'data': df,
                                                       'price': price})
            resp.append(r)
        for r in resp:
            await r

    def handle_message(self, content: SimpleBid, meta):
        if content.volume != 0:
            self.bids.append({
                'price': content.price,
                'volume': content.volume,
                'sender_id': meta['sender_id']
            })

    def handle_list_message(self, content: list[SimpleBid], meta):
        for bid in content:
            self.handle_message(bid, meta)


class BiddingRole(Role):
    def __init__(self, receiver_addr, receiver_id, volume=100, price=0.05):
        super().__init__()
        self.receiver_addr = receiver_addr
        self.receiver_id = receiver_id
        self.volume = volume
        self.price = price

    def setup(self):
        self.context.volume = self.volume
        self.context.price = self.price
        self.context.subscribe_message(
            self, self.handle_message, lambda content, meta: isinstance(content, dict)
        )

    def handle_message(self, content, meta):
        # print(f'Received a message with the following content: {content}.')
        self.context.schedule_instant_task(coroutine=self.set_bids())

    async def set_bids(self):
        price = self.context.price + 0.01 * self.context.price * np.random.random()

        acl_metadata = {
            'performative': Performatives.inform,
            'sender_id': self.context.aid,
            'sender_addr': ('localhost', 5555),
            'conversation_id': 'conversation01'
        }
        await self.context.send_acl_message(receiver_addr=self.receiver_addr,
                                            receiver_id=self.receiver_id,
                                            acl_metadata=acl_metadata,
                                            content=SimpleBid(price, self.context.volume)
                                            )


class BiddingAgent(RoleAgent):
    def __init__(self, container, receiver_addr, receiver_id, volume=100, price=0.05, suggested_aid=None):
        super().__init__(container, suggested_aid=suggested_aid)
        self.add_role(BiddingRole(receiver_addr, receiver_id, volume, price))


class MarketAgent(RoleAgent):
    def __init__(self, container, start: datetime, suggested_aid=None):
        super().__init__(container, suggested_aid=suggested_aid)
        self.add_role(TwoSidedMarketRole(start))


class IntermediaryMarketAgent(RoleAgent):
    def __init__(self, container, start: datetime, receiver_addr, receiver_id, suggested_aid=None):
        super().__init__(container, suggested_aid=suggested_aid)
        self.add_role(TwoSidedMarketRole(start))
        self.add_role(BiddingRole(receiver_addr, receiver_id, 0, 0))


async def main(start: datetime):
    clock = ExternalClock(start_time=start.timestamp())

    # works
    addr = [('127.0.0.1', 5555)]

    # asyncio.exceptions.CancelledError
    # sys:1: RuntimeWarning: coroutine 'TimestampScheduledTask.run' was never awaited
    # sys:1: RuntimeWarning: coroutine 'BiddingAgent.set_bids' was never awaited
    # addr = [('127.0.0.1', 5555), ('127.0.0.1', 5556), ('127.0.0.1', 5557)]
    containers = []
    for ad in addr:
        c = await create_container(addr=ad, clock=clock)
        containers.append(c)
    market = MarketAgent(c, start)

    intermediary_markets = []
    agents = []
    market_receiver_ids = []
    for j in range(5):
        inter_market = IntermediaryMarketAgent(c, start-timedelta(seconds=60),
                                               ad, market.aid, suggested_aid=f'inter{j}')
        intermediary_markets.append(inter_market)

        if j%2==0:
            generation_count=5
            demand_count=7
        else:
            generation_count=7
            demand_count=5

        # asks (generation)
        receiver_ids = []
        for i in range(generation_count):
            ad = addr[i%len(addr)]
            c = containers[i%len(addr)]
            agent = BiddingAgent(c, ad, inter_market.aid, price=0.05*(i%9))
            agents.append(agent)
            receiver_ids.append((ad, agent.aid))

        # bids (demand)
        for i in range(demand_count):
            ad = addr[i%len(addr)]
            c = containers[i%len(addr)]
            agent = BiddingAgent(c, ad, inter_market.aid, volume=-80, price=0.03+0.05*(i%9))
            agents.append(agent)
            receiver_ids.append((ad, agent.aid))
        inter_market._role_context.receiver_ids = receiver_ids

        market_receiver_ids.append((ad, inter_market.aid))
    # and inter_markets to upper_market
    market._role_context.receiver_ids = market_receiver_ids

    if isinstance(clock, ExternalClock):
        for i in range(100):
            await asyncio.sleep(0.0001)
            clock.set_time(clock.get_next_activity() or clock.time+1)
    await c.shutdown()
    print(market._role_context.results)
    import matplotlib.pyplot as plt
    fig, ax1 = plt.subplots()
    plt.title(f'Simulation Results {market.aid}')
    plt.plot(market._role_context.results, label='price')
    ax2 = ax1.twinx()
    plt.plot(market._role_context.demands, label='demand', c='r')
    plt.legend()
    plt.show()
    for i in intermediary_markets:
        fig, ax1 = plt.subplots()
        plt.title(f'Simulation Results {i.aid}')
        plt.plot(i._role_context.results, label='price')
        ax2 = ax1.twinx()
        plt.plot(i._role_context.demands, label='demand', c='r')
        plt.legend()
        plt.show()



if __name__ == '__main__':
    start = parse('202301010000')
    asyncio.run(main(start))
