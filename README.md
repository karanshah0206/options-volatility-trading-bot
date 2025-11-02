# Algorithmic Volatility Options Trading Bot

Python volatility‑arbitrage trading bot for the **Rotman Interactive Trading (RIT)** simulator. The bot trades listed options on the RTM ETF, exploiting mismatches between **implied volatility (IV)** and **realized volatility (RV)** using theoretical Black‑Scholes pricing, delta hedging, and automated risk control.

## Features

* Connects to RIT via REST (requests), reads tick status, securities, trader state, and news
* Computes theoretical option values via **Black‑Scholes** and estimates **Delta (Greeks)**
* Trades mispriced calls/puts when IV ≠ RV (volatility arbitrage)
* Delta‑neutral hedging using RTM ETF to manage directional exposure
* Automated position management: open, scale, unwind when converged or profitable
* Weekly realized‑vol update parsing from RIT news feed
* Hard risk caps (delta limits, per‑order limits, quantity control)
* Runs event‑loop aligned to tick stream (~2–3 Hz)

## Instruments

* **RTM** (underlying ETF)
* **RTM48C, RTM49C, RTM50C, RTM51C, RTM52C** (calls)
* **RTM48P, RTM49P, RTM50P, RTM51P, RTM52P** (puts)

## How it works (high‑level)

* Waits for market ACTIVE status
* Each tick:

  * Pulls quotes & positions
  * Updates time‑to‑expiry and realized vol (when announced)
  * Calculates theoretical Black‑Scholes value + Delta
  * If mispricing ≥ threshold, opens long/short vol position
  * Adjusts target price as trade evolves
  * Hedges net delta using RTM shares when exposure > limit
  * Unwinds hedges when no longer needed

## Requirements

* Python 3.9+
* pandas, requests, numpy, scipy

```
pip install pandas requests numpy scipy
```

## Configuration

Edit constants in the script:

* API endpoint: `http://localhost:9999/v1/`
* Header: `{"X-API-Key": "YOUR_KEY"}`
* Trading params: `OPTIONS_QTY_PER_TRADE`, `NET_DELTA_RISK_LIMIT`, `SHARES_ORDER_LIMIT`, etc.

Example:

```python
API_KEY = {"X-API-Key": "REPLACE_ME"}
OPTIONS_QTY_PER_TRADE = 90
NET_DELTA_RISK_LIMIT = 5000
```

## Run

1. Start the RIT case locally
2. Set API key in script
3. Run: `python main.py`

Bot trades until tick limit or case shutdown.

## Strategy Details

* **Volatility arbitrage**: long options when market < theoretical, short when > theoretical
* **Delta‑neutral hedging**: adjusts RTM position to offset option delta
* **Realized vol updates**: auto‑parsed from RIT news at weekly intervals
* **Exit logic**: close trades when target met or spread collapses

## Notes & Assumptions

* Risk‑free rate assumed 0 for competition case
* VWAP‑based hedge unwind logic to capture residual P&L
* Time‑to‑expiry modeled from tick countdown
* Uses top‑of‑book only; no depth modeling

## Extending

* Add volatility surface / smiles
* Implement Vega hedging or gamma scalping
* Add P&L logging & visualization
* Backtesting harness

## Disclaimer

For educational/simulation use only. Not financial advice. Trade at your own risk.
