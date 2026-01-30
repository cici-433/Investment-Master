import akshare as ak
import pandas as pd

try:
    print("Testing stock_research_report_em...")
    # 尝试获取个股研报，例如 600519 (茅台)
    # 注意：akshare 的接口参数可能变动，先尝试无参或标准参数
    df = ak.stock_research_report_em(symbol="600519")
    print(df.head())
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
    # 尝试备用接口
    try:
        print("Testing stock_news_em...")
        df = ak.stock_news_em(symbol="600519")
        print(df.head())
    except Exception as e2:
        print(f"Error 2: {e2}")
