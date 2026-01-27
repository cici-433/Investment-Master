import yfinance as yf
import json

def check_dividend(ticker):
    print(f"Checking {ticker}...")
    stock = yf.Ticker(ticker)
    info = stock.info
    
    keys = [k for k in info.keys() if 'dividend' in k.lower() or 'yield' in k.lower()]
    result = {k: info[k] for k in keys}
    
    print(json.dumps(result, indent=2))

check_dividend("600036.SS")
check_dividend("002027.SZ")
