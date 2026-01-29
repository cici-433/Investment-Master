from .selection import StockSelector
from .valuation import Valuator
from .analysis import Analyzer
from .portfolio_manager import PortfolioManager
from .system_manager import SystemManager
from .journal_manager import JournalManager

class InvestmentMaster:
    def __init__(self):
        # self.selector = StockSelector()
        self.valuator = Valuator()
        # self.analyzer = Analyzer()
        self.portfolio = PortfolioManager()
        self.system_manager = SystemManager()
        self.journal_manager = JournalManager()

    def _normalize_ticker(self, ticker):
        """
        标准化股票代码，自动为 A 股代码添加后缀
        """
        ticker = ticker.strip().upper()
        
        # 特殊处理：现金
        if ticker == 'CASH':
            return ticker

        # 如果已经是标准格式（包含点）或不是6位数字，直接返回
        if '.' in ticker or not ticker.isdigit() or len(ticker) != 6:
            return ticker
            
        # 简单的 A 股规则判断
        if ticker.startswith(('60', '68')):
            new_ticker = f"{ticker}.SS"
            print(f"提示: 自动将 {ticker} 转换为 {new_ticker} (沪市)")
            return new_ticker
        elif ticker.startswith(('00', '30')):
            new_ticker = f"{ticker}.SZ"
            print(f"提示: 自动将 {ticker} 转换为 {new_ticker} (深市)")
            return new_ticker
        elif ticker.startswith(('5')):
            new_ticker = f"{ticker}.SS"
            print(f"提示: 自动将 {ticker} 转换为 {new_ticker} (沪市ETF/基金)")
            return new_ticker
        elif ticker.startswith(('15')):
            new_ticker = f"{ticker}.SZ"
            print(f"提示: 自动将 {ticker} 转换为 {new_ticker} (深市ETF/基金)")
            return new_ticker
        elif ticker.startswith(('4', '8')):
             # 北交所通常是 .BJ，但 yfinance 支持可能有限，先尝试转换
            new_ticker = f"{ticker}.BJ"
            print(f"提示: 自动将 {ticker} 转换为 {new_ticker} (北交所)")
            return new_ticker
            
        return ticker

    def run_stock_selection(self):
        print("\n--- 启动选股助手 ---")
        # 这里可以交互式获取用户输入，例如市场、板块、指标
        criteria = {
            'min_pe': 0,
            'max_pe': 50,
            'min_roe': 15
        }
        print(f"默认筛选标准: {criteria}")
        
        tickers_input = input("请输入要筛选的股票代码列表 (逗号分隔，留空使用模拟数据): ")
        if tickers_input.strip():
            tickers = [self._normalize_ticker(t) for t in tickers_input.split(',')]
        else:
            tickers = None
        
        results = self.selector.select(criteria, tickers)
        print("筛选结果:")
        if not results:
            print("没有找到符合条件的股票。")
        for stock in results:
            print(f"- {stock}")

    def run_valuation(self):
        print("\n--- 启动估值工具 ---")
        ticker = input("请输入股票代码 (例如 AAPL, 600519.SS): ")
        if not ticker:
            return
        
        ticker = self._normalize_ticker(ticker)
        
        print(f"正在获取 {ticker} 数据...")
        price = self.valuator.get_current_price(ticker)
        pe_data = self.valuator.calculate_pe(ticker)
        dcf_data = self.valuator.calculate_dcf(ticker)
        pb_data = self.valuator.calculate_pb_roe(ticker)
        
        print(f"\n====== 估值报告: {ticker} ======")
        print(f"当前市场价格: {price}")
        
        if pe_data:
            print("\n[基本面数据 (Fundamental)]")
            print(f"  行业: {pe_data.get('sector')}")
            print(f"  Trailing PE: {pe_data.get('trailing_pe')}")
            print(f"  Forward PE: {pe_data.get('forward_pe')}")
            print(f"  Current PB: {pe_data.get('price_to_book')}")
            print(f"  ROE: {pe_data.get('return_on_equity')}")
        else:
            print("\n[基本面数据] 无法获取")

        if pb_data and "error" not in pb_data:
            print("\n[PB-ROE 估值法分析]")
            print(f"  1. 计算规则说明:")
            print(f"     - 核心公式: 合理 PB = (ROE x 100) / 7")
            print(f"     - 逻辑: 假设 ROE 与 PB 呈线性关系，使用 7 作为保守分母因子")
            
            print(f"\n  2. 详细计算过程:")
            print(f"     - 输入 ROE: {pb_data['current_roe']*100:.2f}%")
            print(f"     - 计算合理 PB: {pb_data['current_roe']*100:.2f} / 7 = {pb_data['target_pb']}x")
            print(f"     - 当前实际 PB: {pb_data['current_pb']:.2f}x")
            
            print(f"\n  3. 估值结论:")
            print(f"     [买入信号] (合理 PB 的 70%-80%)")
            print(f"       目标: {pb_data['target_pb']}x * 0.7 ~ 0.8")
            print(f"       范围: {pb_data['buy_range_pb'][0]}x ~ {pb_data['buy_range_pb'][1]}x")
            
            print(f"     [卖出信号] (合理 PB 的 120%-130%)")
            print(f"       目标: {pb_data['target_pb']}x * 1.2 ~ 1.3")
            print(f"       范围: {pb_data['sell_range_pb'][0]}x ~ {pb_data['sell_range_pb'][1]}x")
            
            print(f"  ------------------------------------------------")
            print(f"  当前 PB 溢价率: {pb_data['margin']:+.2f}%")
            print(f"  (注: 股价 = PB x 每股净资产 {pb_data['bps']:.2f})")
            print(f"  参考买入价: {pb_data['buy_range_price'][0]} ~ {pb_data['buy_range_price'][1]}")
            
            if pb_data['margin'] > 30:
                 print("  >>> 结论: 严重低估 (PB 维度)")
            elif pb_data['margin'] > 0:
                 print("  >>> 结论: 轻微低估 (PB 维度)")
            else:
                 print("  >>> 结论: 高估 (PB 维度)")
        elif pb_data and "error" in pb_data:
            print(f"\n[PB-ROE 分析] 无法计算: {pb_data['error']}")

        if dcf_data and "error" not in dcf_data:
            params = dcf_data["parameters"]
            res = dcf_data["result"]
            term = dcf_data["terminal_value"]
            
            print("\n[DCF 现金流折现模型分析]")
            print("  注意: 本模型仅作演示，使用粗略假设，不构成投资建议。")
            print("\n  1. 关键假设参数:")
            print(f"     - 初始自由现金流 (FCF): {params['initial_fcf']:,.2f}")
            print(f"     - 预测期增长率 (Growth Rate): {params['growth_rate']*100}%")
            print(f"     - 加权平均资本成本 (WACC): {params['wacc']*100}%")
            print(f"     - 永续增长率 (Terminal Growth): {params['terminal_growth']*100}%")
            
            print("\n  2. 未来现金流预测与折现:")
            print(f"     {'年份':<5} | {'预测 FCF':<15} | {'折现因子':<10} | {'现值 (PV)':<15}")
            print("     " + "-"*55)
            for step in dcf_data["steps"]:
                print(f"     {step['year']:<5} | {step['fcf']:<15,.2f} | {step['discount_factor']:<10.4f} | {step['present_value']:<15,.2f}")
            
            print("\n  3. 终值 (Terminal Value) 计算:")
            print(f"     - 预测期末 FCF: {dcf_data['steps'][-1]['fcf']:,.2f}")
            print(f"     - 终值 (TV): {term['future_value']:,.2f}")
            print(f"     - 终值现值 (TV PV): {term['present_value']:,.2f}")
            
            print("\n  4. 估值汇总:")
            print(f"     - 预测期现金流现值总和: {res['sum_pv_cash_flows']:,.2f}")
            print(f"     - (+) 终值现值: {term['present_value']:,.2f}")
            print(f"     - (=) 企业/股权价值 (简化): {res['total_equity_value']:,.2f}")
            print(f"     - (/) 总股本: {res['shares_outstanding']:,.0f}")
            print(f"     - (=) 每股理论公允价值 (Intrinsic Value): {res['fair_value_per_share']}")
            
            fair_value = res['fair_value_per_share']
            print(f"\n  5. 安全边际分析 (Margin of Safety):")
            print(f"     当前股价: {price}")
            print(f"     理论价值: {fair_value}")
            
            # 计算不同安全边际下的买入价格
            margins = [0.15, 0.30, 0.50]
            print(f"\n     建议买入价格参考:")
            print(f"     {'安全边际':<10} | {'折扣率':<10} | {'建议买入价':<15} | {'当前溢价/折价':<15}")
            print("     " + "-"*60)
            
            for m in margins:
                buy_price = fair_value * (1 - m)
                diff_pct = ((price - buy_price) / buy_price) * 100 if buy_price else 0
                status = "低估(可买)" if price < buy_price else "高估(观望)"
                print(f"     {m*100:<3.0f}%       | {(1-m)*100:<3.0f}%折     | {buy_price:<15.2f} | {status}")

            current_margin = ((fair_value - price) / fair_value) * 100 if fair_value else 0
            print(f"\n  >>> 结论: 当前价格隐含的安全边际为 {current_margin:.2f}%")
            if current_margin < 0:
                print(f"      (警告: 当前价格 {price} 高于理论价值 {fair_value}，无安全边际)")
            elif current_margin < 30:
                print(f"      (提示: 安全边际不足 30%，建议谨慎)")
            else:
                print(f"      (利好: 安全边际充足，具备投资价值)")
            
        elif dcf_data and "error" in dcf_data:
            print(f"\n[DCF 分析] 无法计算: {dcf_data['error']}")
        else:
             print("\n[DCF 分析] 无法获取足够数据进行计算")

        # 6. 市赚率 (PR) 分析
        # info 可能在前面的步骤中未定义（如果 dcf_data 计算失败或者直接跳过），这里重新获取或确保 info 存在
        # 但 calculate_pr 内部会处理 info=None 的情况
        pr_data = self.valuator.calculate_pr(ticker, info if 'info' in locals() else None)
        if pr_data and "error" not in pr_data:
            print("\n[市赚率 (PR) 估值分析]")
            print(f"  1. 计算规则说明:")
            print(f"     - 核心公式: PR = N x PE / (ROE x 100)")
            print(f"     - 修正系数 N 规则 (以 50% 分红率为基准):")
            print(f"       * 分红率 >= 50% -> N = 1.0")
            print(f"       * 分红率 <= 25% -> N = 2.0")
            print(f"       * 25% < 分红率 < 50% -> N = 0.5 / 分红率")

            print(f"\n  2. 详细计算过程:")
            dpr_val = pr_data['dpr']*100 if pr_data['dpr'] else 0
            print(f"     - 输入数据: PE={pr_data['pe']:.2f}, ROE={pr_data['roe']*100:.2f}%, 分红率={dpr_val:.1f}%")
            
            # 显示 N 的计算逻辑
            n_logic = ""
            if dpr_val >= 50: n_logic = ">= 50%, 取 1.0"
            elif dpr_val <= 25: n_logic = "<= 25%, 取 2.0"
            else: n_logic = f"0.5 / {pr_data['dpr']:.2f} = {pr_data['n_factor']:.2f}"
            print(f"     - 计算系数 N: {n_logic}")
            
            # 显示 PR 的计算
            print(f"     - 计算 PR: {pr_data['n_factor']:.2f} x ({pr_data['pe']:.2f} / {pr_data['roe']*100:.2f})")
            print(f"     - 结果 PR: {pr_data['pr_value']}")

            print(f"\n  3. 估值结论:")
            print(f"     >>> {pr_data['result_type']}")
            print(f"     (判定标准: PR < 0.6 买入, 0.6-1.0 持有, > 1.0 卖出)")
        elif pr_data and "error" in pr_data:
            print(f"\n[PR 分析] 无法计算: {pr_data['error']}")
            
        print("\n" + "="*50)

    def run_analysis(self):
        print("\n--- 启动分析报告 ---")
        ticker = input("请输入股票代码或行业名称: ")
        if not ticker:
            return
        
        ticker = self._normalize_ticker(ticker)
        
        report = self.analyzer.generate_report(ticker)
        print("\n分析简报:")
        print(report)
