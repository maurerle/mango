import asyncio
import logging
import time

import matplotlib.pyplot as plt
import pandas as pd

from tests.integration_tests.test_single_container_termination import (
    distribute_ping_pong_test,
    distribute_ping_pong_test_timestamp,
)

results = []

rename = {
    "distribute_ping_pong_test_timestamp": "clock synchronisation",
    "distribute_ping_pong_test": "direct ping pong",
}

EXEC_RUNTIME_STUDY = False

if EXEC_RUNTIME_STUDY:
    for func in [distribute_ping_pong_test, distribute_ping_pong_test_timestamp]:
        for max_count in [
            1,
            2,
            25,
            50,
            100,
            200,
            300,
            400,
            500,
            600,
            700,
            800,
            900,
            1000,
            5000,
            10000,
        ]:
            for connection_type in ["tcp", "mqtt"]:
                if max_count > 1000 and connection_type == "mqtt":
                    continue
                print(connection_type, max_count, func.__name__)
                t = time.time()
                asyncio.run(func(connection_type, max_count=max_count))
                duration = time.time() - t
                results.append(
                    [rename[func.__name__], connection_type, max_count, duration]
                )
else:
    logging.getLogger("mango").setLevel(logging.INFO)
    logging.basicConfig(format="%(asctime)s;%(levelname)s;%(message)s")
    connection_type = "mqtt"
    max_count = 10
    func = distribute_ping_pong_test_timestamp
    print(connection_type, max_count, func.__name__)
    t = time.time()
    asyncio.run(func(connection_type, max_count=max_count))
    duration = time.time() - t
    results.append([func.__name__, connection_type, max_count, duration])

df = pd.DataFrame(results, columns=["function", "connection_type", "count", "duration"])
df["roundtrip_per_second"] = df["count"] / df["duration"]
print(df)
if EXEC_RUNTIME_STUDY:
    df.to_csv("runtime.csv", index=None)

SAVE_FIG = True

if SAVE_FIG:
    df = pd.read_csv("runtime.csv")
    pivot_df = df.pivot(columns=["function", "connection_type"], index="count")
    # substract duration with 1 message (shows overhead)
    startup_duration = pivot_df["duration"].loc[1]
    print(startup_duration)
    diff = pivot_df["duration"] - pivot_df["duration"].loc[1]
    # recalculate roundtrip per second
    inverse_df = 1 / diff.div(diff.index.values, axis=0)
    pivot_df["roundtrip_per_second"] = inverse_df
    # remove index=1 which is infinity
    pivot_df = pivot_df.drop(1)
    pivot_df["roundtrip_per_second"][pivot_df.index <= 1000].plot(
        figsize=(10, 5), grid=True
    )
    plt.ylabel("roundtrips per second")
    plt.title("roundtrips by technology and method")
    plt.savefig("roundtrip_per_seconds.svg")

    pivot_df["duration"].plot(figsize=(10, 5), grid=True)
    plt.savefig("duration.svg")


# Function to create LaTeX table from Series with MultiIndex
def series_to_latex(series):
    latex_table = "\\begin{table}[h]\n\\centering\n\\begin{tabular}{lll}\n\\hline\n"
    latex_table += "\\textbf{Function} & \\textbf{Connection Type} & \\textbf{Value} \\\\\n\\hline\n"

    current_function = ""
    for (function, connection_type), value in series.items():
        if function != current_function:
            if current_function:
                latex_table += "\\hline\n"
            latex_table += f"\\multirow{{2}}{{*}}{{{function}}} & {connection_type} & {value:.6f} \\\\\n"
            current_function = function
        else:
            latex_table += f" & {connection_type} & {value:.6f} \\\\\n"

    latex_table += "\\hline\n\\end{tabular}\n"
    latex_table += "\\caption{Function and Connection Type Data}\n"
    latex_table += "\\label{tab:startup_duration}\n"
    latex_table += "\\end{table}"

    return latex_table


# Generate and print the LaTeX table
latex_output = series_to_latex(startup_duration)
print(latex_output)

# Optionally, save to a file
with open("startup_duration.tex", "w") as f:
    f.write(latex_output)
