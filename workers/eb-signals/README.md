# EB Signals

Cloudflare Worker that builds the daily snapshot read by the EB Investment Dashboard (Framer): `GET /signals`.

## Sources (free, public display allowed with attribution)

- Currencies: European Central Bank; USD/RUB: Bank of Russia
- Crypto: CoinGecko (Demo API)
- World stock markets: OECD share price indices via FRED (monthly)
- Energy: U.S. EIA spot prices via FRED
- Government bond yields: U.S. Treasury, ECB, Bank of England, OECD via FRED
- Market Mood: Chicago Fed NFCI credit subindex, St. Louis Fed Financial Stress Index (via FRED)
- Metals: EB Metals Worker (service binding `METALS`)

## Settings in Cloudflare (never in this repository)

| Name | Type | Use |
|---|---|---|
| `RUN_TOKEN` | Secret | protects `/signals/run`, `/signals/check`, `/signals/refresh-yields` |
| `COINGECKO_KEY` | Secret | optional, higher CoinGecko limits |
| `ALERT_WEBHOOK` | Variable | ntfy.sh topic, Discord or Slack webhook for the daily check |
| `ALERT_HOUR`, `ALERT_TZ`, `ALERT_IGNORE` | Variables | daily check time, time zone, assets never reported (default `Russia`) |
| `FINNHUB_KEY`, `TWELVE_KEY`, `TWELVE_LICENSED` | Secrets / variable | only with a licence for public display |

## Useful addresses

- `/signals/health`: setup check, snapshot summary and `problems`
- `/signals/run?token=…` (`&reset=1` to start the day again): one step of the job
- `/signals/check?token=…&test=1`: run the daily check now and send a test message
