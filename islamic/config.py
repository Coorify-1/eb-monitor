"""EB Islamic Investment: settings. Change the method here.

Everything a reader sees is computed from public data, except the yearly industry
figures below (IFSB, IIFM), which are copied from their published reports.
"""

# ---------------------------------------------------------------- Halal screen (United States)

MIN_MARKET_CAP_USD = 10e9     # same universe as EB Monitor: New York listings worth more than $10bn
CANDIDATES = 1500             # most traded New York listings looked at
INDEX_MEMBERS = 100           # EB Shariah US 100
INDEX_CAP = 0.08              # no company above 8% of the index

# AAOIFI Shari'a Standard No. 21, market value as denominator (12-month average)
DEBT_LIMIT = 30.0             # interest-bearing debt / market value, %
CASH_LIMIT = 30.0             # cash + interest-bearing securities / market value, %
NPI_LIMIT = 5.0               # non-permissible (interest) income / revenue, %
WATCH_MARGIN = 5.0            # "Watch" when a ratio is within 5 points of its limit (1 point for income)

# Business screen: conventional finance and insurance, alcohol, tobacco, pork, gambling,
# weapons and adult entertainment. SEC industry codes (SIC) first, then named companies.
EXCLUDED_SIC = [
    (6000, 6411, "Conventional finance or insurance"),
    (6700, 6797, "Conventional finance"),
    (6799, 6799, "Conventional finance"),
    (2082, 2085, "Alcohol"),
    (5180, 5182, "Alcohol"),
    (2100, 2199, "Tobacco"),
    (5194, 5194, "Tobacco"),
    (3480, 3489, "Weapons"),
    (3760, 3769, "Weapons"),
    (7840, 7841, "Adult entertainment risk"),
]
# Companies whose main business is excluded but whose industry code does not show it.
# One per line in spirit: TICKER: reason. Editable.
EXCLUDED_TICKERS = {
    # alcohol
    "STZ": "Alcohol", "BF.B": "Alcohol", "BF-B": "Alcohol", "BF.A": "Alcohol", "DEO": "Alcohol",
    "BUD": "Alcohol", "TAP": "Alcohol", "SAM": "Alcohol", "MGPI": "Alcohol",
    # tobacco and cannabis
    "MO": "Tobacco", "PM": "Tobacco", "BTI": "Tobacco", "TPB": "Tobacco",
    # gambling
    "LVS": "Gambling", "WYNN": "Gambling", "MGM": "Gambling", "CZR": "Gambling", "PENN": "Gambling",
    "BYD": "Gambling", "RRR": "Gambling", "CHDN": "Gambling", "DKNG": "Gambling", "FLUT": "Gambling",
    "MLCO": "Gambling", "LNW": "Gambling", "BRSL": "Gambling", "IGT": "Gambling", "MCRI": "Gambling",
    "GLPI": "Gambling", "VICI": "Gambling",
    # weapons and defence
    "LMT": "Weapons", "NOC": "Weapons", "GD": "Weapons", "LHX": "Weapons", "HII": "Weapons",
    "RTX": "Weapons", "RGR": "Weapons", "SWBI": "Weapons",
    # pork
    "TSN": "Pork", "HRL": "Pork", "SFD": "Pork",
    # conventional finance listed under other industry codes
    "BRK.B": "Conventional insurance", "BRK-B": "Conventional insurance", "BRK.A": "Conventional insurance",
    "SPGI": "Conventional finance", "MCO": "Conventional finance", "MSCI": "Conventional finance",
    "ICE": "Conventional finance", "CME": "Conventional finance", "NDAQ": "Conventional finance",
    "COIN": "Conventional finance", "HOOD": "Conventional finance", "SOFI": "Conventional finance",
    # music and cinema
    "WMG": "Music and cinema", "LYV": "Music and cinema", "AMC": "Music and cinema", "CNK": "Music and cinema",
    "IMAX": "Music and cinema", "SPOT": "Music and cinema",
}

# XBRL concepts read from SEC filings (us-gaap, latest quarter for balance-sheet items)
DEBT_TAGS = {
    "lt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations",
                      "LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermDebtAndCapitalLeaseObligationsNoncurrent"],
    "lt_total": ["LongTermDebt", "LongTermDebtAndFinanceLeasesObligations"],
    "lt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "debt_current": ["DebtCurrent", "ShortTermBorrowingsAndCurrentPortionOfLongTermDebt"],
    "short": ["ShortTermBorrowings", "CommercialPaper"],
}
CASH_TAGS = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "st_inv": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
               "HeldToMaturitySecuritiesCurrent"],
    "lt_inv": ["MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
               "HeldToMaturitySecuritiesNoncurrent"],
}
REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]
INTEREST_INCOME_TAGS = ["InvestmentIncomeInterest", "InvestmentIncomeInterestAndDividend",
                        "InterestIncomeOther", "InterestIncomeOperating", "InterestAndOtherIncome"]
SHARES_TAGS = [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")]

# IFRS equivalents for foreign companies that file annual reports with the SEC (20-F, 40-F)
FX_FALLBACK = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"

IFRS = {
    "debt": ["NoncurrentPortionOfNoncurrentBorrowings", "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
             "LongtermBorrowings", "ShorttermBorrowings", "Borrowings"],
    "cash": ["CashAndCashEquivalents"],
    "inv": ["CurrentInvestments", "OtherCurrentFinancialAssets"],
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers"],
    "interest": ["InterestIncome", "RevenueFromInterest", "FinanceIncome"],
}

# ---------------------------------------------------------------- Islamic funds (SEC Form N-PORT)

FUNDS = [
    # ticker, short name, issuer, kind
    ("SPUS", "S&P 500 Shariah", "SP Funds", "ETF"),
    ("HLAL", "FTSE USA Shariah", "Wahed", "ETF"),
    ("MNZL", "Russell Halal USA", "Manzil", "ETF"),
    ("SPTE", "Global Technology", "SP Funds", "ETF"),
    ("SPWO", "World ex-US", "SP Funds", "ETF"),
    ("UMMA", "Dow Jones Islamic World", "Wahed", "ETF"),
    ("SPRE", "Global REIT Shariah", "SP Funds", "ETF"),
    ("SPSK", "Global Sukuk", "SP Funds", "ETF"),
    ("AMAGX", "Amana Growth", "Saturna", "Mutual fund"),
    ("AMANX", "Amana Income", "Saturna", "Mutual fund"),
    ("AMDWX", "Amana Developing World", "Saturna", "Mutual fund"),
    ("AMAPX", "Amana Participation (sukuk)", "Saturna", "Mutual fund"),
]
FUND_FILINGS_BACKFILL = 14    # N-PORT reports read the first time (each holds 3 months of returns)

# ---------------------------------------------------------------- Official Shariah lists

SC_PAGE = "https://www.sc.com.my/development/icm/icm-publications/list-of-shariah-compliant-securities"
OJK_PAGE = "https://www.ojk.go.id/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Default.aspx"
DFM_API = "https://api2.dfm.ae/web/widgets/v1/data"
DFM_PAGE = "https://www.dfm.ae/en/the-exchange/statistics-reports/sharia-classification-list"

# ---------------------------------------------------------------- Rates (Bank Negara Malaysia)

BNM_API = "https://api.bnm.gov.my/public"
BNM_TERMS = "https://www.bnm.gov.my/terms-of-use-bnm-datasets"
RATES_MONTHS = 24

# ---------------------------------------------------------------- News (GDELT)

NEWS_QUERY = ('(sukuk OR "islamic finance" OR "islamic bank" OR "islamic banking" OR "shariah-compliant" '
              'OR "sharia-compliant" OR "shariah compliant" OR takaful OR AAOIFI OR IFSB OR "halal investing") '
              'sourcelang:english')
NEWS_MAX = 8
NEWS_TAGS = [
    ("Sukuk", r"\bsukuk\b"),
    ("Takaful", r"\btakaful\b"),
    ("Funds", r"\b(fund|etf|asset manag|portfolio)"),
    ("Rules", r"\b(aaoifi|ifsb|regulat|standard|central bank|fatwa|shariah board|sharia board)"),
    ("Banking", r"\bbank"),
    ("Markets", r"."),
]

# ---------------------------------------------------------------- Industry figures (yearly, from reports)
# Update these when IFSB (May) and IIFM (spring) publish their new reports.

INDUSTRY = {
    "assets": {
        "label": "Islamic finance assets",
        "unit": "USD trillion",
        "points": [["2023", 3.38], ["2024", 3.88], ["2025", 4.4]],
        "source": "IFSB, Islamic Financial Stability Report 2026 and IFSI Stability Reports 2024–2025",
        "url": "https://www.ifsb.org/?p=40644",
    },
    "growth2025": {
        "label": "Growth in 2025",
        "rows": [["Islamic funds", 25.6], ["Sukuk outstanding", 21.8], ["Islamic banking", 9.7], ["Whole industry", 13.4]],
        "source": "IFSB, Islamic Financial Stability Report 2026",
        "url": "https://www.ifsb.org/wp-content/uploads/2026/05/IFSR-2026.pdf",
    },
    "mix": {
        "label": "Industry mix",
        "year": "2024",
        "rows": [["Islamic banking", 71.6], ["Sukuk", 23.3], ["Funds and takaful", 5.1]],
        "source": "IFSB, IFSI Stability Report 2025",
        "url": "https://www.ifsb.org/download/ifsi-stability-report-2025/",
    },
    "sukuk": {
        "outstanding": 1015.5,  # USD billion, end 2025 (international 280.58 + domestic 734.93)
        "issuance": [["2024", 205.0], ["2025", 262.9]],
        "issuers": [["Malaysia", 43.69], ["Saudi Arabia", 15.33], ["Indonesia", 9.62]],
        "issuersNote": "Share of all sukuk issued, 2001–2025",
        "source": "IIFM Sukuk Report, 15th edition (2026)",
        "url": "https://www.iifm.net/",
    },
}
