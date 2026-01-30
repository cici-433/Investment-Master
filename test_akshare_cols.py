import akshare as ak
import pandas as pd

try:
    df = ak.stock_research_report_em(symbol="600519")
    print(df.columns.tolist())
    print(df.iloc[0])
except Exception as e:
    print(e)
