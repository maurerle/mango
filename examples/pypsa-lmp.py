# -*- coding: utf-8 -*-
## Simple electricity market examples
#
# This Jupyter notebook is meant for teaching purposes. To use it, you need to install a Python environment with Jupyter notebooks, and the Python for Power System Analysis (PyPSA) library. See
#
# https://pypsa.readthedocs.io/en/latest/installation.html
#
# for tips on installation.
#
# It gradually builds up more and more complicated energy-only electricity markets in PyPSA, starting from a single bidding zone, going up to multiple bidding zones connected with transmission (NTCs) along with variable renewables and storage.
#
# Available as a Jupyter notebook at https://pypsa.readthedocs.io/en/latest/examples/simple-electricity-market-examples.ipynb.

### Preliminaries
#
# Here libraries are imported and data is defined.

import numpy as np

import pypsa

from datetime import datetime, date, timedelta
import pandas as pd
snapshots = list(pd.date_range(start =date.today()-timedelta(days=1),end =date.today(), freq ='1H'))

# marginal costs in EU
marginal_costs = {"Wind": 0, "Hydro": 0, "Coal": 30, "Gas": 60, "Oil": 80}

# power plant capacities (nominal powers in MW) in each country (not necessarily realistic)
power_plant_p_nom = {
    "South Africa": {"Coal": 35000, "Wind": 3000, "Gas": 8000, "Oil": 2000},
    "Mozambique": {
        "Hydro": 1200,
    },
    "Swaziland": {
        "Hydro": 600,
    },
}

# transmission capacities in MW (not necessarily realistic)
transmission = {
    "South Africa": {"Mozambique": 500, "Swaziland": 250},
    "Mozambique": {"Swaziland": 100},
    "Swaziland": {},
}

# country electrical loads in MW (not necessarily realistic)
loads = {"South Africa": 42000, "Mozambique": 650, "Swaziland": 250}
df = pd.DataFrame(loads, index=snapshots)
df['Swaziland'].iloc[8:17] *=3
loads = df
### Single bidding zone with fixed load, one period
#
# In this example we consider a single market bidding zone, South Africa.
#
# The inelastic load has essentially infinite marginal utility (or higher than the marginal cost of any generator).

country = "South Africa"

network = pypsa.Network()
network.snapshots=snapshots
network.add("Bus", country)

for tech in power_plant_p_nom[country]:
    network.add(
        "Generator",
        "{} {}".format(country, tech),
        bus=country,
        p_nom=power_plant_p_nom[country][tech],
        marginal_cost=marginal_costs[tech],
    )


network.add("Load", "{} load".format(country), bus=country, p_set=loads[country])

# Run optimisation to determine market dispatch
network.lopf()

# print the load active power (P) consumption
network.loads_t.p

# print the generator active power (P) dispatch
network.generators_t.p

# print the clearing price (corresponding to gas)
network.buses_t.marginal_price

### Two bidding zones connected by transmission, one period
#
# In this example we have bidirectional transmission capacity between two bidding zones. The power transfer is treated as controllable (like an A/NTC (Available/Net Transfer Capacity) or HVDC line). Note that in the physical grid, power flows passively according to the network impedances.

network = pypsa.Network()
network.snapshots=snapshots
countries = ["Mozambique", "South Africa", "Swaziland"]

for country in countries:

    network.add("Bus", country)

    for tech in power_plant_p_nom[country]:
        network.add(
            "Generator",
            "{} {}".format(country, tech),
            bus=country,
            p_nom=power_plant_p_nom[country][tech],
            marginal_cost=marginal_costs[tech],
        )

    network.add("Load", "{}d load".format(country), bus=country, p_set=loads[country])

    # add transmission as controllable Link
    if country not in transmission:
        continue

    for other_country in countries:
        if other_country not in transmission[country]:
            continue

        # NB: Link is by default unidirectional, so have to set p_min_pu = -1
        # to allow bidirectional (i.e. also negative) flow
        network.add(
            "Link",
            "{} - {} link".format(country, other_country),
            bus0=country,
            bus1=other_country,
            p_nom=transmission[country][other_country],
            p_min_pu=-1,
        )

network.lopf()

network.loads_t.p

network.generators_t.p.plot()
network.loads_t.p_set
network.links_t.p0.plot()

# print the clearing price (corresponding to water in Mozambique and gas in SA)
network.buses_t.marginal_price.plot()

# link shadow prices
network.links_t.mu_lower

network.plot()