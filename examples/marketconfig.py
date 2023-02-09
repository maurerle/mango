from mango import Agent
from datetime import datetime, timedelta
from dateutil import rrule
import logging
from dataclasses import dataclass
from typing import Callable
from numpy.typing import ArrayLike

logger = logging.getLogger(__name__)


class MarketAgent(Agent):
    longitude: float
    latitude: float


@dataclass
class MarketProduct():
    delivery_start_time: datetime
    delivery_end_time: datetime
    price: float
    volume: float


# describe the configuration of a market product which is available at a market

@dataclass
class MarketProductConfig:
    product_duration: str # quarter-hourly, half-hourly, hourly, 4hourly, daily, weekly, monthly, quarter-yearly, yearly
    product_future_count: int # how many future durations can be traded
    # TODO how should this represent the actual config of what it means?


# Class for a Smart Contract which can contain something like:
# - Contract for Differences (CfD) -> based on market result
# - Market Subvention -> based on market result
# - Power Purchase Agreements (PPA) -> A buys everything B generates for price x
# - Swing Contract ->

contracttype = Callable[[Agent, Agent], None]
marketcontracttype = Callable[[Agent, Agent, ArrayLike], None]
eligable_lambda = Callable[Agent, bool]


def ppa(buyer: Agent, seller: Agent):
    set_price = 26 # ct/kWh
    buyer.generation += seller.generation
    seller.revenue += seller.generation * set_price
    buyer.revenue -= seller.generation * set_price
    seller.generation = 0

def swingcontract(buyer: Agent, seller: Agent):
    set_price = 26 # ct/kWh
    outer_price = 45 # ct/kwh
    if minDCQ < buyer.demand and buyer.demand < maxDCQ:
        cost = buyer.demand * set_price
    else:
        cost = outer_price
    buyer.revenue -= buyer.demand*cost
    seller.revenue += buyer.demand*cost

def cfd(buyer: Agent, seller: Agent, market_index):
    set_price = 26 # ct/kWh
    cost = set_price - market_index
    seller.revenue += cost
    buyer.revenue -= cost

def eeg(buyer: Agent, seller: Agent, market_index):
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
    maximum_gradient: float = None
    maximum_volume: int = 500
    additional_fields: list[str] = []
    available_market_products: list[MarketProduct]
    amount_unit: str
    price_unit: str
    price_tick: float = 0.1 # steps in which the price can be increased
    continuous: bool = True # <- each market gets cleared "immediately", if a timeslot closes, the next one begins
    eligable_obligations_lambda: eligable_lambda
    lambda: agent.payed_fee
    # obligation should be time-based 
    # nur regelenergie bieten wenn für die gleiche Stunde Regelleistung von diesem Agent gebraucht wurde


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
    maximum_gradient=0.1,
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
    continuous=True, # approximationsgrad
    # wann zurück ziehen?
    # Welche bedingungen gelten hierfür?
    amount_unit='0.1 MWh',
    price_unit='€/MWh',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
)
# pay as bid
# publishes market results to TSO every 15 minutes
# matching findet nur in eigener Regelzone für die letzen 15 Minuten statt - sonst mindestens 30 Minuten vorher


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
    additional_fields=['sender_id', 'eligable_lambda', 'contract'], # agent_id, eligable_lambda, MarketContract/Contracttype
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
    # laufzeit vs abrechnungszeitraum
)

# Control Reserve market
# regelleistung kann 7 Tage lang geboten werden (überschneidende Gebots-Zeiträume)?
# FCR
market_start = today - timedelta(days=7) + timedelta(hours=10)
control_reserve_trading_config = MarketConfig(
    today,
    additional_fields=['eligable_lambda'], # eligable_lambda
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
market_start = today - timedelta(days=2) + timedelta(hours=12)
control_work_trading_config = MarketConfig(
    today,
    additional_fields=['eligable_lambda'],
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
    # obligation = innerhalb von 1 minute reagieren kann
) # pay-as-bid/merit-order

# MISO Nodal market
# https://help.misoenergy.org/knowledgebase/article/KA-01024/en-us
market_start = today - timedelta(days=14) + timedelta(hours=10, minutes=30)

miso_day_ahead_config = MarketConfig(
    today,
    additional_fields=['node_id'],
    available_market_products=[
        MarketProduct('hourly', 24),
    ],
    continuous=False,
    opening_hours=rrule.rrule(rrule.DAILY, market_start),
    opening_duration=timedelta(days=1),
    amount_unit='MW',
    price_unit='$/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
    eligable_lambda=lambda agent: agent.location
) # pay-as-bid/merit-order

# ISO gibt spezifisches Marktergebnis welches nicht teil des Angebots war

# Contour Map
# https://www.misoenergy.org/markets-and-operations/real-time--market-data/markets-displays/
# Realtime Data API
# https://www.misoenergy.org/markets-and-operations/RTDataAPIs/
# SCED
# https://help.misoenergy.org/knowledgebase/article/KA-01112/en-us
# Market Closure Table (unclear)
# https://help.misoenergy.org/knowledgebase/article/KA-01163/en-us
# Metrics:
# https://cdn.misoenergy.org/202211%20Markets%20and%20Operations%20Report627372.pdf (p. 60-63)
miso_real_time_config = MarketConfig(
    today,
    additional_fields=['node_id'],
    available_market_products=[
        MarketProduct('5minutes', 12),
        # unclear how many slots can be traded?
        # at least the current hour
    ],
    continuous=False,
    opening_hours=rrule.rrule(rrule.MINUTELY, interval=5, dtstart=today-timedelta(hours=1)),
    opening_duration=timedelta(hours=1),
    amount_unit='MW',
    price_unit='$/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
    eligable_lambda=lambda agent: agent.location in BW,
    clearing = "twoside_clearing"
) # pay-as-bid/merit-order


result_bids = clearing(self, input_bids)

# double auction clearing
# symmetrical auction
def twoside_clearing(market_agent):
    #if not df.empty:
    # simple merit order calculation
    # generation
    market_agent.config.opening_hours:

    additional_fields=['node_id'],
    available_market_products=[
        MarketProduct('hourly', 24),
    ],
    continuous=False,
    opening_hours=rrule.rrule(rrule.DAILY, market_start),
    opening_duration=timedelta(days=1),
    amount_unit='MW',
    price_unit='$/MW',
    price_tick=0.01,
    maximum_bid=9999,
    minimum_bid=-9999,
    eligable_lambda=lambda agent: agent.location
) # pay-as-bid/merit-order

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

    return [(agent, 50, volume), (agent, 20, volume)]


# asymmetrical auction
# one sided acution

lmp_market
nodes


# GME market - italian
# which market products exist?
#


# PJM: https://pjm.com/markets-and-operations/energy/real-time/historical-bid-data/unit-bid.aspx
# DataMiner: https://dataminer2.pjm.com/feed/da_hrl_lmps/definition
# ContourMap: https://pjm.com/markets-and-operations/interregional-map.aspx

# TODO: ISO NE, ERCOT, CAISO


## Agenten müssen ihren Verpflichtungen nachkommen
## TODO: geographische Voraussetzungen - wer darf was - Marktbeitrittsbedingungen





# LMP Markt:
# https://www.e-education.psu.edu/eme801/node/498
# Alle Contraints und marginal Costs werden gesammelt
# Markt dispatched kosten an Demand nach Stability constrained Merit-Order
# Teilnehmer werden nur mit Marginal Costs bezahlt
# differenz ist congestion revenue -> behält TSO ein?

# All operating facilities in the U.S. devote the first portion of their revenues to the maintenance and operations of the priced lanes. 
# The traffic monitoring, tolling, enforcement, incident management, administration, and routine maintenance costs can be significant,
# https://www.cmap.illinois.gov/updates/all/-/asset_publisher/UIMfSLnFfMB6/content/examples-of-how-congestion-pricing-revenues-are-used-elsewhere-in-the-u-s-


# Virtual profitability Index:
# sum of all profits (transactions settled above price) / Total traded MWh


# Which roles do you need for the market

