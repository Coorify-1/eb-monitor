# EB Monitor

Weekly ranking engine for **Economic Bearings**: the top 5 banks and top 5 companies, ranked by the EB Method.
Every Monday at 7:00 am New York it publishes `docs/eb-monitor.json`, which the EB Monitor component on the website reads.

**Data URL for the Framer component:**
`https://raw.githubusercontent.com/Coorify-1/eb-monitor/main/docs/eb-monitor.json`

## The EB Method

Universe: shares listed in New York (NYSE, Nasdaq) worth more than $10bn, including foreign companies that file with the SEC (20-F, 40-F). Every figure comes from the companies' official filings.

Each pillar is scored 0–100 against peers (percentile; companies against their sector). The EB Score is the weighted average.

| Banking Monitor | Weight | Measured by |
|---|---|---|
| Valuation | 25% | Price / tangible book, P/E |
| Momentum | 25% | 12-month return skipping the last month, gap to the 200-day average |
| Capital | 20% | CET1 ratio, tangible equity / assets |
| Asset quality | 15% | Non-performing loans / loans, provisions / loans |
| Profitability | 15% | Return on equity, return on assets |

| Company Monitor (non-financial) | Weight | Measured by |
|---|---|---|
| Valuation | 30% | Free-cash-flow yield, EV / EBIT |
| Momentum | 30% | As above |
| Quality | 20% | Return on invested capital, stability of operating margin |
| Health | 20% | Net debt / EBITDA, Piotroski F-score, Altman Z-score |

Rules: a pick keeps its place while it stays in the top 10; at most 2 picks per country (and per sector for companies); a company needs data for at least 75% of the pillar weight. Settings live in `engine/config.py`.

The *why* and *risks* lines are generated from the numbers, not written by hand.

## Sources

- SEC EDGAR (company filings, public domain)
- Massive, free Stocks Basic plan (end-of-day prices; used to compute scores, raw prices are not published)
- Wikidata (CC0) for leaders, staff numbers and websites; portraits from Wikimedia Commons only under free licences, with credit
- FRED (St. Louis Fed) for the market regime; ECB reference rates (Frankfurter) for currency conversion

## How it runs

`.github/workflows/weekly.yml` runs every Monday and can also be started by hand (Actions → EB Monitor weekly → Run workflow).
Price history is kept on the `cache` branch so each week only fetches a few new days. The first run takes about 2 hours.

Secrets needed: `MASSIVE_API_KEY`, `SEC_CONTACT`.

Files published in `docs/`: `eb-monitor.json` (this week), `history/` (every week, for the track record), `eb-ranking-full.json` (top 30 scores), `CHECK.md` (weekly editorial check list with links to the sources).

Editorial corrections (CEO, chair, website, name, country, city) go in `data/overrides.json`; they win over automatic data.

*Educational content ranked by a published method, not investment advice.*
