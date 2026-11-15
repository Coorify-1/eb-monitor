"""EB Method settings: weights, filters, data tags. Change the method here."""

MIN_MARKET_CAP_USD = 10e9      # only large companies
CANDIDATES = 700               # most traded US listings checked each week
PICKS = 5
KEEP_IF_IN_TOP = 10            # a pick keeps its place while it stays in the top 10
MAX_PER_COUNTRY = 2
MAX_PER_SECTOR = 2             # companies only
MIN_WEIGHT_COVERAGE = 0.75     # share of pillar weight that must have data

BANK_PILLARS = [
    # key, label, weight
    ("valuation", "Valuation", 25),
    ("momentum", "Momentum", 25),
    ("capital", "Capital", 20),
    ("quality", "Asset quality", 15),
    ("profit", "Profitability", 15),
]
COMPANY_PILLARS = [
    ("valuation", "Valuation", 30),
    ("momentum", "Momentum", 30),
    ("quality", "Quality", 20),
    ("health", "Health", 20),
]

BANK_SIC = {6021, 6022, 6029, 6035, 6036}


def is_financial(sic: int) -> bool:
    return 6000 <= sic <= 6799


def sector_of(sic: int) -> str:
    """Broad sector from the SEC industry code (SIC)."""
    s = int(sic or 0)
    if s in BANK_SIC:
        return "Banks"
    if 6000 <= s <= 6799:
        return "Financials"
    if 1300 <= s <= 1399 or 2900 <= s <= 2999:
        return "Energy"
    if 4900 <= s <= 4999:
        return "Utilities"
    if 2830 <= s <= 2836 or 3841 <= s <= 3851 or 8000 <= s <= 8099 or s == 5122:
        return "Health care"
    if 3570 <= s <= 3579 or 3600 <= s <= 3699 or 7370 <= s <= 7379 or 3820 <= s <= 3829:
        return "Technology"
    if 4800 <= s <= 4899 or 2700 <= s <= 2799 or 7800 <= s <= 7899:
        return "Communication"
    if 2000 <= s <= 2199 or 5400 <= s <= 5499 or 5900 <= s <= 5912 or 2840 <= s <= 2844:
        return "Consumer staples"
    if (
        2200 <= s <= 2399 or 3100 <= s <= 3199 or 3710 <= s <= 3716 or 3900 <= s <= 3999
        or 5200 <= s <= 5999 or 7000 <= s <= 7299 or 7900 <= s <= 7999
    ):
        return "Consumer discretionary"
    if 1000 <= s <= 1499 or 2400 <= s <= 2699 or 2800 <= s <= 2899 or 3000 <= s <= 3399:
        return "Materials"
    if 1500 <= s <= 1799 or 3400 <= s <= 3999 or 4000 <= s <= 4799 or 5000 <= s <= 5199 or 7300 <= s <= 7399 or 8700 <= s <= 8799:
        return "Industrials"
    return "Other"


# XBRL concepts, tried in order (us-gaap for US filers, ifrs-full for foreign filers).
TAGS = {
    "revenue": [
        ("us-gaap", "Revenues"),
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
        ("us-gaap", "SalesRevenueNet"),
        ("us-gaap", "RevenuesNetOfInterestExpense"),
        ("us-gaap", "OilAndGasRevenue"),
        ("us-gaap", "RevenueFromContractWithCustomerProductAndServiceExcludingAssessedTax"),
        ("ifrs-full", "Revenue"),
        ("ifrs-full", "RevenueFromContractsWithCustomers"),
        ("ifrs-full", "RevenueFromSaleOfGoods"),
    ],
    "gross_profit": [("us-gaap", "GrossProfit"), ("ifrs-full", "GrossProfit")],
    "operating_income": [
        ("us-gaap", "OperatingIncomeLoss"),
        ("ifrs-full", "ProfitLossFromOperatingActivities"),
    ],
    "pretax_income": [
        ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),
        ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
        ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"),
        ("ifrs-full", "ProfitLossBeforeTax"),
    ],
    "net_income": [
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic"),
        ("us-gaap", "ProfitLoss"),
        ("ifrs-full", "ProfitLossAttributableToOwnersOfParent"),
        ("ifrs-full", "ProfitLoss"),
    ],
    "cfo": [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
        ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"),
    ],
    "capex": [
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
        ("us-gaap", "PaymentsToAcquireProductiveAssets"),
        ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
        ("ifrs-full", "PurchaseOfPropertyPlantAndEquipment"),
    ],
    "da": [
        ("us-gaap", "DepreciationDepletionAndAmortization"),
        ("us-gaap", "DepreciationAndAmortization"),
        ("us-gaap", "DepreciationAmortizationAndAccretionNet"),
        ("us-gaap", "Depreciation"),
        ("ifrs-full", "DepreciationAndAmortisationExpense"),
        ("ifrs-full", "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"),
    ],
    "interest_expense": [
        ("us-gaap", "InterestExpense"),
        ("us-gaap", "InterestExpenseNonoperating"),
        ("us-gaap", "InterestExpenseDebt"),
        ("ifrs-full", "FinanceCosts"),
        ("ifrs-full", "InterestExpense"),
    ],
    "assets": [("us-gaap", "Assets"), ("ifrs-full", "Assets")],
    "current_assets": [("us-gaap", "AssetsCurrent"), ("ifrs-full", "CurrentAssets")],
    "current_liabilities": [("us-gaap", "LiabilitiesCurrent"), ("ifrs-full", "CurrentLiabilities")],
    "liabilities": [("us-gaap", "Liabilities"), ("ifrs-full", "Liabilities")],
    "equity": [
        ("us-gaap", "StockholdersEquity"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        ("ifrs-full", "EquityAttributableToOwnersOfParent"),
        ("ifrs-full", "Equity"),
    ],
    "retained_earnings": [
        ("us-gaap", "RetainedEarningsAccumulatedDeficit"),
        ("ifrs-full", "RetainedEarnings"),
    ],
    "cash": [
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        ("ifrs-full", "CashAndCashEquivalents"),
    ],
    "debt_long": [
        ("us-gaap", "LongTermDebtNoncurrent"),
        ("us-gaap", "LongTermDebt"),
        ("us-gaap", "LongTermDebtAndCapitalLeaseObligations"),
        ("ifrs-full", "NoncurrentPortionOfNoncurrentBorrowings"),
        ("ifrs-full", "LongtermBorrowings"),
        ("ifrs-full", "NoncurrentFinancialLiabilities"),
    ],
    "debt_short": [
        ("us-gaap", "LongTermDebtCurrent"),
        ("us-gaap", "DebtCurrent"),
        ("us-gaap", "ShortTermBorrowings"),
        ("ifrs-full", "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"),
        ("ifrs-full", "ShorttermBorrowings"),
    ],
    "goodwill": [("us-gaap", "Goodwill"), ("ifrs-full", "Goodwill")],
    "intangibles": [
        ("us-gaap", "IntangibleAssetsNetExcludingGoodwill"),
        ("us-gaap", "FiniteLivedIntangibleAssetsNet"),
        ("ifrs-full", "IntangibleAssetsOtherThanGoodwill"),
    ],
    # banks
    "loans": [
        ("us-gaap", "LoansAndLeasesReceivableNetReportedAmount"),
        ("us-gaap", "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss"),
        ("us-gaap", "LoansAndLeasesReceivableNetOfDeferredIncome"),
        ("us-gaap", "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss"),
        ("ifrs-full", "LoansAndAdvancesToCustomers"),
    ],
    "deposits": [("us-gaap", "Deposits"), ("ifrs-full", "DepositsFromCustomers")],
    "allowance": [
        ("us-gaap", "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest"),
        ("us-gaap", "AllowanceForLoanAndLeaseLosses"),
        ("us-gaap", "FinancingReceivableAllowanceForCreditLosses"),
    ],
    "nonaccrual": [
        ("us-gaap", "FinancingReceivableExcludingAccruedInterestNonaccrual"),
        ("us-gaap", "FinancingReceivableRecordedInvestmentNonaccrualStatus"),
    ],
    "provision": [
        ("us-gaap", "ProvisionForLoanLeaseAndOtherLosses"),
        ("us-gaap", "ProvisionForLoanAndLeaseLosses"),
        ("us-gaap", "FinancingReceivableCreditLossExpenseReversal"),
        ("us-gaap", "ProvisionForCreditLosses"),
        ("ifrs-full", "ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9"),
    ],
    "noninterest_expense": [("us-gaap", "NoninterestExpense"), ("ifrs-full", "OperatingExpense")],
    "net_interest_income": [
        ("us-gaap", "InterestIncomeExpenseNet"),
        ("us-gaap", "InterestIncomeExpenseAfterProvisionForLoanLoss"),
        ("ifrs-full", "InterestRevenueExpense"),
        ("ifrs-full", "NetInterestIncome"),
    ],
    "noninterest_income": [("us-gaap", "NoninterestIncome"), ("ifrs-full", "FeeAndCommissionIncomeExpense")],
    "cet1_ratio": [
        ("us-gaap", "BankingRegulationCommonEquityTierOneRiskBasedCapitalRatioActual"),
        ("us-gaap", "CommonEquityTierOneCapitalRatio"),
        ("us-gaap", "CommonEquityTierOneCapitalToRiskWeightedAssets"),
    ],
    "tier1_ratio": [
        ("us-gaap", "BankingRegulationTier1RiskBasedCapitalRatioActual"),
        ("us-gaap", "TierOneRiskBasedCapitalToRiskWeightedAssets"),
    ],
}

FLOW = {
    "revenue", "gross_profit", "operating_income", "pretax_income", "net_income", "cfo",
    "capex", "da", "interest_expense", "provision", "noninterest_expense",
    "net_interest_income", "noninterest_income",
}
RATIO = {"cet1_ratio", "tier1_ratio"}
