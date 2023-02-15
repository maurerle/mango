import logging
from datetime import datetime, timedelta
from itertools import groupby
from math import isclose
from typing import TypedDict

from dateutil import relativedelta, rrule
from marketconfig import MarketConfig, MarketProduct, MarketOrderbook, Orderbook, Order

from mango import Role

logger = logging.getLogger(__name__)


def is_mod_close(a, mod_b):
    '''
    due to floating point, a mod b can be very close to 0 or very close to mod_b
    '''
    abs_tol=1e-14
    # abs_tol needed for comparison near zero
    return isclose(a % mod_b, 0, abs_tol=abs_tol ) or isclose(a % mod_b, mod_b, abs_tol=abs_tol)


class OpeningMessage(TypedDict):
    context: str
    market_id: str
    start: float
    stop: float
    products: list[MarketProduct]


class ClearingMessage(TypedDict):
    context: str
    market_id: str
    orderbook: Orderbook

# can be extended with custom config fields


orderbook: MarketOrderbook = {
    'agent1': [
        {
            'start_time': datetime.now(),
            'end_time': datetime.now(),
            'volume': 100,
            'price': 50.4,
        },
        {
            'start_time': datetime.now(),
            'end_time': datetime.now(),
            'volume': 100,
            'price': 50.4,
        }
    ],
    'agent2': [
        {
            'start_time': datetime.now(),
            'end_time': datetime.now(),
            'volume': 100,
            'price': 50.4,
        },
        {
            'start_time': datetime.now(),
            'end_time': datetime.now(),
            'volume': 100,
            'price': 50.4,
        }
    ]
}


class MarketRole(Role):
    pass


def cumsum(orderbook: Orderbook):
    sum_ = 0
    for order in orderbook:
        sum_ += order['volume']
        order['cumsum'] = sum_
    return orderbook


def twoside_clearing(market_agent: MarketRole):
    bids = filter(lambda x: x['volume'] < 0, market_agent.all_orders)
    asks = filter(lambda x: x['volume'] > 0, market_agent.all_orders)
    # volume 0 is ignored/invalid

    # generation
    sorted_asks = sorted(asks, key=lambda i: i['price'])

    # demand
    sorted_bids = sorted(bids, key=lambda i: i['price'], reverse=True)

    sorted_asks = cumsum(sorted_asks)
    sorted_bids = cumsum(sorted_bids)
    accepted_orders = []
    price = 0
    demand = 0
    intersection_found = False
    for i in range(len(sorted_bids)):
        total_vol = sorted_bids[i]['cumsum']
        # get first price to match demand (vol)

        for ask in sorted_asks:
            if ask['cumsum'] >= -total_vol:
                assert price <= ask['price'], 'wrong order'
                price = ask['price']
                demand = total_vol
                accepted_orders.append(ask)
            else:
                intersection_found = True
                break
        if intersection_found:
            break

        accepted_orders.append(sorted_bids[i])
    if price == 0:
        price = market_agent.marketconfig.maximum_bid
    meta = {
        'volume': demand,
        'price': price
    }
    return accepted_orders, meta


available_strategies = {
    'one_side_market': 'TODO',
    'two_side_market': twoside_clearing,
    'pay_as_bid': twoside_clearing,  # TODO
    'pay_as_clear': twoside_clearing,
    'nodal_market': 'TODO',

}


def get_available_products(market_products: list[MarketProduct], startdate: datetime):
    options = []
    for product in market_products:
        start = startdate + product.first_delivery_after_start
        if isinstance(product.duration, rrule.rrule):
            starts = list(product.duration.xafter(start, product.count+1))
            for i in range(product.count):
                period_start = starts[i]
                period_end = starts[i+1]
                options.append((period_start, period_end, product.only_hours))
        else:
            for i in range(product.count):
                period_start = start + product.duration * i
                period_end = start + product.duration * (i + 1)
                options.append((period_start, period_end, product.only_hours))
    return options


# add role per Market
class MarketRole(Role):
    longitude: float
    latitude: float
    markets: list = []

    def __init__(self, marketconfig: MarketConfig):
        if isinstance(marketconfig.market_mechanism, str):
            strategy = available_strategies.get(marketconfig.market_mechanism)
            if not strategy:
                raise Exception(f'invalid strategy {marketconfig.market_mechanism}')
            marketconfig.market_mechanism = strategy

        self.marketconfig: MarketConfig = marketconfig
        self.registered_agents: list[str] = []
        self.open_slots = []
        self.all_orders: list[Order] = []
        self.order_book: MarketOrderbook = {}
        self.market_result: Orderbook = []

    def setup(self):
        def accept_orderbook(content: dict, meta):
            if not isinstance(content, dict):
                return False
            name_match = content.get('market') == self.marketconfig.name
            orderbook_exists = content.get('orderbook') is not None
            return name_match and orderbook_exists

        def accept_registration(content: dict, meta):
            if not isinstance(content, dict):
                return False
            return content.get('context') == 'registration' and content.get('market') == self.marketconfig.name

        self.context.subscribe_message(self, self.handle_orderbook, accept_orderbook)
        self.context.subscribe_message(
            self, self.handle_registration, accept_registration
            # TODO safer type check? dataclass?
        )
        current = datetime.fromtimestamp(self.context.current_timestamp)
        next_opening = self.marketconfig.opening_hours.after(current + timedelta(days=1))
        self.context.schedule_timestamp_task(self.next_opening(), next_opening.timestamp())

    async def next_opening(self):
        current = datetime.fromtimestamp(self.context.current_timestamp)
        next_opening = self.marketconfig.opening_hours.after(current)
        if not next_opening:
            logger.info(f"market {self.marketconfig.name} - does not reopen")
            return

        market_closing = next_opening + self.marketconfig.opening_duration
        products = get_available_products(self.marketconfig.market_products, next_opening)
        opening_message = {
            'context': 'opening',
            'market': self.marketconfig.name,
            'start': current,
            'stop': market_closing,
            'products': products
        }
        self.context.schedule_timestamp_task(self.clear_market(), market_closing.timestamp())
        self.context.schedule_timestamp_task(self.next_opening(), next_opening.timestamp())
        logger.info(f"market {self.marketconfig.name} - {next_opening} - {market_closing}")

        for agent in self.registered_agents:
            agent_addr, agent_id = agent
            await self.context.send_acl_message(
                opening_message,
                agent_addr,
                receiver_id=agent_id,
                acl_metadata={"sender_addr": self.context.addr, "sender_id": self.context.aid}
            )

    def handle_registration(self, content: str, meta):
        agent = meta["sender_id"]
        agent_addr = meta["sender_addr"]
        # TODO allow accessing agents properties?
        if self.marketconfig.eligable_obligations_lambda(agent):
            self.registered_agents.append((agent_addr, agent))

    def handle_orderbook(self, content, meta):
        orderbook: Orderbook = content['orderbook']
        # TODO check if agent is allowed to bid
        agent_addr = meta["sender_addr"]
        agent_id = meta["sender_id"]
        try:
            for order in orderbook:
                order['agent_id'] = (agent_addr, agent_id)

                assert is_mod_close(order['volume'], self.marketconfig.amount_tick), 'amount_tick'
                assert is_mod_close(order['price'], self.marketconfig.price_tick), 'price_tick'
                assert order['price'] <= self.marketconfig.maximum_bid, 'max_bid'
                assert order['price'] >= self.marketconfig.minimum_bid, 'min_bid'
                assert abs(order['volume']) <= self.marketconfig.maximum_volume, 'max_volume'
                for field in self.marketconfig.additional_fields:
                    assert order[field], f'missing field: {field}'
                self.all_orders.append(order)
            self.order_book[agent_id] = orderbook
        except Exception as e:
            logger.error(f"error handling message from {agent_id} - {e}")
            self.context.schedule_instant_acl_message(
                content={'context': 'Rejected'},
                receiver_addr=agent_addr,
                receiver_id=agent_id,
                acl_metadata={"sender_addr": self.context.addr, "sender_id": self.context.aid, "reply_to": 1}
            )

    async def clear_market(self):
        self.market_result, market_meta = self.marketconfig.market_mechanism(self)

        for agent, accepted_orderbook in groupby(self.market_result, lambda o: o['agent_id']):
            addr, aid = agent
            meta = {"sender_addr": self.context.addr, "sender_id": self.context.aid}

            await self.context.send_acl_message(
                {
                    'context': 'clearing',
                    'market': self.marketconfig.name,
                    'orderbook': list(accepted_orderbook),
                },
                receiver_addr=addr,
                receiver_id=aid,
                acl_metadata=meta,
            )

        # clear_price = sorted(self.market_result, lambda o: o['price'])[0]
        logger.info(f'clearing price for {self.marketconfig.name} is {market_meta["price"]}, volume: {market_meta["volume"]}')
        # TODO store metrics about latest clearing
