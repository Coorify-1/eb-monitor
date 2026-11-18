"""GEOPOLITICAL RISK MONITOR — settings.

Everything a non-developer may want to change lives here or in the JSON files next to it:
  risks.json     the risks followed: news query and the three assets tied to each risk
  calendar.json  major geopolitical dates (only the big ones)
  events.json    past events marked on the "Global attention over time" chart
  override.json  set a level or a short view by hand for one risk (wins over the data)
"""

# ------------------------------------------------------------------ sources
GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
HISTORY_START = "2017-01-01"     # the GDELT news archive searchable by the API starts here

# ------------------------------------------------------------------ attention
# Each risk gets a weekly score: its share of world news coverage compared with its own
# history (z-score of the log).
WINDOW_WEEKS = 260               # five years of history
HALF_LIFE_WEEKS = None           # None = every week of the five years weighs the same (a long crisis stays visible)
MIN_WEEKS = 26                   # history needed before a score is published
TONE_WEIGHT = 0.0                # weight of negative tone (0 = coverage share only)
REFRESH_DAYS = 42                # each week, the last six weeks are fetched again
FIRST_DAYS = 730                 # a new risk starts with two years, enough to publish at once
GDELT_BUDGET_MIN = 10            # minutes of the Monday run spent on older history (the nightly run does the rest)
GLOBAL_SMOOTH = 0.35             # smoothing of the global line (share of the newest week)

# ------------------------------------------------------------------ market reaction
MOVE_DAYS = 30                   # one-month move (calendar days)
VOL_DAYS = 730                   # usual size of one-month moves, measured over two years
FULL_Z = 2.0                     # a move of 2x its usual one-month size counts in full
DEFAULT_MONTH_VOL = {"price": 6.0, "level": 25.0}   # % or bp, when history is too short

# ------------------------------------------------------------------ level (same rule as the Framer component)
LEVEL_HIGH = 1.0
LEVEL_MEDIUM = 0.4

# ------------------------------------------------------------------ schedule
PUBLISH_WEEKDAY = 0              # Monday
PUBLISH_HOUR_NY = 6              # 06:15 New York
PUBLISH_MINUTE_NY = 15
UA = "Mozilla/5.0 (compatible; EconomicBearings-Geopolitics/1.0)"

SOURCES = ("Attention: the EB Geopolitical Attention Index tracks the relative frequency of news stories "
           "associated with each risk across global print, broadcast and online media in more than 60 "
           "languages (GDELT Project), scored against its five-year history. "
           "Market reaction: one-month moves in the three scenario assets tied to each risk, measured "
           "against their usual volatility. Market data: Federal Reserve Bank of St. Louis (FRED), "
           "COMEX and LME metal prices. Calendar: official calendars of governments and international "
           "institutions.")
