from mango import Agent
from datetime import datetime, timedelta
from dateutil import rrule
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SimpleBid:
    price: float
    volume: float


# describe a market

@dataclass
class MarketProduct:
    product_duration: str # quarter-hourly, half-hourly, hourly, 4hourly, daily, weekly, monthly, quarter-yearly, yearly
    product_future_count: int # how many future durations can be traded
    # TODO how should this represent the actual config of what it means?


# Class for a Smart Contract which can contain something like:
# - Contract for Differences (CfD) -> based on market result
# - Market Subvention -> based on market result
# - Power Purchase Agreements (PPA) -> A buys everything B generates for price x
# - Swing Contract ->
class Contract:
    name: str

    def callback(self, buyer: Agent, seller: Agent):
        raise NotImplementedError()


class PPA(Contract):
    name: str

    def callback(self, buyer: Agent, seller: Agent):
        set_price = 26 # ct/kWh
        buyer.generation += seller.generation
        seller.revenue += seller.generation * set_price
        seller.generation = 0


class SwingContract(Contract):
    name: str

    def callback(self, buyer: Agent, seller: Agent):
        set_price = 26 # ct/kWh
        outer_price = 45 # ct/kwh
        if minDCQ < buyer.demand and buyer.demand < maxDCQ:
            cost = buyer.demand * set_price
        else:
            outer_price


class MarketContract:
    name: str

    def callback(self, buyer: Agent, seller: Agent, market_index):
        raise NotImplementedError()


class CfD(MarketContract):
    name: str

    def callback(self, buyer: Agent, seller: Agent, market_index):
        set_price = 26 # ct/kWh
        cost = set_price - market_index
        seller.revenue += cost
        buyer.revenue -= cost


class EEG(MarketContract):
    name: str

    def callback(self, buyer: Agent, seller: Agent, market_index):
        set_price = 26 # ct/kWh
        cost = set_price - market_index
        if cost > 0:
            seller.revenue += cost
            buyer.revenue -= cost


d = datetime.now()
today = datetime(d.year, d.month, d.day)


@dataclass
class MarketConfig:
    start_date: datetime  # start of delivery products
    end_date: datetime = None
    maximum_bid: float = 9999
    minimum_bid: float = -500
    maximum_gradiend: float = 0.1
    maximum_volume: int = 500
    additional_fields: list[str] = []
    available_market_products: list[MarketProduct]
    amount_unit: str
    price_unit: str
    price_tick: float = 0.1 # steps in which the price can be increased
    continuous: bool = True # <- each market gets cleared "immediately", if a timeslot closes, the next one begins

    # if not continous
    opening_hours: rrule.rrule  # dtstart must be relative to start_date
    open_duration: timedelta
    market_mechanism: str
    # if continuous: one of [pay_as_bid, pay_as_ask] else: pay_as_clear


# relevant information
# https://www.next-kraftwerke.de/wissen/spotmarkt-epex-spot
# https://www.epexspot.com/sites/default/files/2023-01/22-10-25_TradingBrochure.pdf

# EPEX DayAhead-Auction:
# https://www.epexspot.com/en/tradingproducts#day-ahead-trading
market_start = today - timedelta(days=2) + timedelta(hours=12)

epex_dayahead_auction_config = MarketConfig(
    today,
    additional_fields=['link', 'offer_id'],
    available_market_products=[MarketProduct('hourly', 24)],
    continuous=False,
    opening_hours=rrule.rrule(rrule.DAILY, market_start),
    opening_duration=timedelta(days=1),
    amount_unit='0.1 MWh',
    price_unit='€/MW',
)
# uniform pricing/merit order

# EPEX Intraday-Auction:
# https://www.epexspot.com/en/tradingproducts#intraday-trading
market_start = today - timedelta(days=2) + timedelta(hours=15)

epex_intraday_auction_config = MarketConfig(
    today,
    available_market_products=[MarketProduct('quarter-hourly', 96)],
    continuous=False,
    opening_hours=rrule.rrule(rrule.DAILY, market_start),
    opening_duration=timedelta(days=1),
    amount_unit='0.1 MWh',
    price_unit='€/MWh',
    price_tick=0.01,
    maximum_bid=4000,
    minimum_bid=-3000

)
# uniform pricing/merit order

# EPEX IntraDay-Trading:
# https://www.epexspot.com/en/tradingproducts#intraday-trading
market_start = today - timedelta(days=1) + timedelta(hours=15)

epex_intraday_trading_config = MarketConfig(
    market_start,
    available_market_products=[
        MarketProduct('quarter-hourly', 96),
        MarketProduct('half-hourly', 48),
        MarketProduct('hourly', 24)
    ],
    continuous=True,
    amount_unit='0.1 MWh',
    price_unit='€/MWh',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
)
# pay as bid
# publishes market results to TSO every 15 minutes



# TerminHandel:
# https://www.eex.com/en/markets/power/power-futures
market_start = today

eex_future_trading_config = MarketConfig(
    today,
    additional_fields=['link', 'offer_id'],
    available_market_products=[
        MarketProduct('daily', 7),
        MarketProduct('weekly', 4),
        MarketProduct('monthly', 9),
        MarketProduct('quarter-yearly', 11),
        MarketProduct('yearly', 10),
    ],
    continuous=True,
    maximum_bid=9999,
    minimum_bid=-9999,
    amount_unit='MW',
    price_unit='0.01 €/MWh',
)
# open from 8:00 to 18:00 on workdays
# https://www.eex.com/en/markets/power/power-futures

# AfterMarket:
# https://www.epexspot.com/en/tradingproducts#after-market-trading
market_start = today + timedelta(hours=1)

epex_aftermarket_trading_config = MarketConfig(
    today,
    additional_fields=['link', 'offer_id'],
    available_market_products=[
        MarketProduct('hourly', 24),
    ],
    amount_unit='0.1 MWh',
    price_unit='€/MWh',
    price_tick=0.01,
    continuous=True,
    maximum_bid=9999,
    minimum_bid=-9999,
)
# Trading end should be 12:30 day after delivery (D+1) but is always +24h now
# XXX market_start is not respected yet

# EPEX Emissionsmarkt Spot:
# EU Allowance (EUA)
# https://www.eex.com/de/maerkte/umweltprodukte/eu-ets-auktionen
# https://www.eex.com/de/maerkte/umweltprodukte/eu-ets-spot-futures-options
# https://www.eex.com/fileadmin/EEX/Markets/Environmental_markets/Emissions_Spot__Futures___Options/20200619-EUA_specifications_v2.pdf

epex_emission_trading_config = MarketConfig(
    today,
    additional_fields=['link', 'offer_id'],
    available_market_products=[
        MarketProduct('yearly', 10),
    ],
    continuous=True,
    amount_unit='t CO2',
    price_unit='€/t',
)

p2p_trading_config = MarketConfig(
    today,
    additional_fields=['sender_id', 'receiver_id'],
    available_market_products=[
        MarketProduct('quarter-hourly', 96),
        MarketProduct('half-hourly', 48),
        MarketProduct('hourly', 24),
    ],
    continuous=True,
    amount_unit='kWh',
    price_unit='€/kWh',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
)

# eligable_lambda is a lambda to check if an agent is eligable to receive a policy (must have solar...)
# TODO define how contracts look like - maybe just a string?
policy_trading_config = MarketConfig(
    today,
    additional_fields=['sender_id', 'eligable_lambda', 'contract'],
    available_market_products=[
        MarketProduct('monthly', 12),
        MarketProduct('quarter-yearly', 1),
        MarketProduct('yearly', 1),
    ],
    continuous=True,
    amount_unit='MW',
    price_unit='€/MWh',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
)

# Control Reserve market
# regelleistung kann 7 Tage lang geboten werden (überschneidende Gebots-Zeiträume)?
market_start = today - timedelta(days=7) + timedelta(hours=10)
control_reserve_trading_config = MarketConfig(
    today,
    available_market_products=[
        MarketProduct('4hourly', 6*7),
    ],
    continuous=False,
    opening_hours=rrule.rrule(rrule.DAILY, market_start),
    opening_duration=timedelta(days=7),
    amount_unit='MW',
    price_unit='€/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
) # pay-as-bid/merit-order one sided

# RAM Regelarbeitsmarkt - Control Reserve
market_start = today - timedelta(days=1) + timedelta(hours=12)
control_work_trading_config = MarketConfig(
    today,
    available_market_products=[
        MarketProduct('quarter-hourly', 96),
    ],
    continuous=False,
    opening_hours=rrule.rrule(rrule.DAILY, market_start),
    opening_duration=timedelta(days=1),
    amount_unit='MW',
    price_unit='€/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
) # pay-as-bid/merit-order
