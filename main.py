import sys
from investment_master.core import InvestmentMaster

def main():
    print("欢迎使用投资大师 (Investment Master)")
    master = InvestmentMaster()
    
    while True:
        print("\n请选择功能:")
        print("1. 选股 (Stock Selection)")
        print("2. 估值 (Valuation)")
        print("3. 公司/行业分析 (Analysis)")
        print("q. 退出")
        
        choice = input("请输入选项: ")
        
        if choice == '1':
            master.run_stock_selection()
        elif choice == '2':
            master.run_valuation()
        elif choice == '3':
            master.run_analysis()
        elif choice.lower() == 'q':
            print("感谢使用，再见！")
            break
        else:
            print("无效选项，请重试。")

if __name__ == "__main__":
    main()
