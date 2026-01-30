import akshare as ak
import pandas as pd
from datetime import datetime

class ReportManager:
    def __init__(self):
        pass

    def get_reports(self, ticker):
        """
        Fetch research reports for a given ticker using AkShare.
        """
        # Ticker format handling: 600519.SS -> 600519
        # AkShare expects just the 6-digit code for A-shares
        symbol = ticker.split('.')[0]
        
        # Only support A-shares for now (6 digits)
        # If it's not numeric or length is not 6, it might be US/HK stock which this API might not support directly
        if not symbol.isdigit() or len(symbol) != 6:
             # Try to see if it works, otherwise return empty
             # Some HK stocks might work with different API, but let's focus on A-shares first
             pass

        try:
            # Fetch reports from EastMoney
            df = ak.stock_research_report_em(symbol=symbol)
            
            if df.empty:
                return []
            
            reports = []
            # Take top 20 reports to avoid too much data
            for _, row in df.head(50).iterrows():
                reports.append({
                    "date": str(row['日期']),
                    "title": row['报告名称'],
                    "org": row['机构'],
                    "rating": row['东财评级'],
                    "link": row['报告PDF链接']
                })
            return reports
        except Exception as e:
            print(f"Error fetching reports for {ticker}: {e}")
            return []
