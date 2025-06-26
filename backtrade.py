import backtrader as bt
import yfinance as yf
import pandas as pd
import os

data_dir = "cached_data"
os.makedirs(data_dir, exist_ok=True)

class FixedQtySizer(bt.Sizer):
    params = (('qty', 1),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        return self.p.qty


class StochasticRSI(bt.Indicator):
    lines = ('stochrsi',)
    params = (('rsi_period', 14), ('stoch_period', 14))

    def __init__(self):
        rsi = bt.indicators.RSI(self.data, period=self.p.rsi_period)
        min_rsi = bt.indicators.Lowest(rsi, period=self.p.stoch_period)
        max_rsi = bt.indicators.Highest(rsi, period=self.p.stoch_period)
        self.lines.stochrsi = (rsi - min_rsi) / (max_rsi - min_rsi + 1e-9) * 100



class RSISRSIStrategy(bt.Strategy):
    params = dict(rsi_jump_threshold=42, price_ma20_threshold=12, price_ma50_threshold=10)

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.srsi = StochasticRSI(self.data, rsi_period=14, stoch_period=14)
        self.ma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=20)
        self.ma50 = bt.indicators.SimpleMovingAverage(self.data.close, period=50)

        self.order = None
        self.buy_price = None
        self.trades = []
        self.bar_executed = 0
        self.hold_days = 10
        self.srsi_extreme_bars = 0
        self.buy_infos = {}

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.rsi[0] < 30 and self.srsi[0] < 30 and self.data.close[0] < self.ma20[0]:
                self.buy_price = self.data.close[0]
                self.buy_rsi = self.rsi[0]
                self.bar_executed = len(self)
                self.order = self.buy()
            
            self.buy_infos[self.data._name] = {
            'Buy Date': self.data.datetime.date(0),
            'Buy Price': self.buy_price,
            }

        else:
            hold_time = len(self) - self.bar_executed
            rsi_jump = self.rsi[0] - self.buy_rsi
            price = self.data.close[0]
            price_vs_ma20 = (price - self.ma20[0]) / self.ma20[0] * 100
            price_vs_ma50 = (price - self.ma50[0]) / self.ma50[0] * 100

            stop_loss_pct = 0.20
            take_profit_pct = 0.20

            take_profit_price = self.buy_price * (1 + take_profit_pct)
            stop_loss_price = self.buy_price * (1 - stop_loss_pct)

            high = self.data.high[0]
            low = self.data.low[0]

            take_profit_triggered = high >= take_profit_price
            stop_loss_triggered = low <= stop_loss_price


            if self.srsi[0] > 80:
                self.srsi_extreme_bars += 1
            else:
                self.srsi_extreme_bars = 0 

            sell_signal = (
                self.rsi[0] > 70 or
                rsi_jump > self.p.rsi_jump_threshold or
                price_vs_ma20 > self.p.price_ma20_threshold or
                price_vs_ma50 > self.p.price_ma50_threshold
            )

            # Determine reason
            if stop_loss_triggered:
                sell_price = stop_loss_price
                exit_reason = "Stop Loss"
            elif take_profit_triggered:
                sell_price = take_profit_price
                exit_reason = "Take Profit"
            elif self.rsi[0] > 70:
                exit_reason = "RSI Overbought"
            elif rsi_jump > self.p.rsi_jump_threshold:
                exit_reason = "RSI Jump"
            elif price_vs_ma20 > self.p.price_ma20_threshold:
                exit_reason = "Price > MA20"
            elif price_vs_ma50 > self.p.price_ma50_threshold:
                exit_reason = "Price > MA50"
            elif sell_signal:
                sell_price = price
                exit_reason = "Signal Exit"
            else:
                exit_reason = "Unknown"

            if sell_signal or stop_loss_triggered or take_profit_triggered:
                if not (take_profit_triggered or stop_loss_triggered):
                    sell_price = price 

                pnl = sell_price - self.buy_price
                self.trades.append({
                    'Entry Date': self.data.datetime.date(-hold_time),
                    'Exit Date': self.data.datetime.date(0),
                    'Buy Price': self.buy_price,
                    'Sell Price': sell_price,
                    'PnL': pnl,
                    'PnL_%': pnl / self.buy_price,
                    'Dollar_PnL': pnl ,
                    'Stopped Out': stop_loss_triggered,
                    'Profit Taken': take_profit_triggered,
                    'Exit Reason': exit_reason

                })
                self.order = self.sell()
                self.srsi_extreme_bars = 0


    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None

    def stop(self):
        if self.trades:
            df = pd.DataFrame(self.trades)
            df['Win'] = df['PnL'] > 0
            df['Ticker'] = self.data._name
            self.trades_df = df 
      


if __name__ == '__main__':
    tickers = [
        'AAPL', 'MSFT', 'NVDA', 'AMD', 'GOOGL', 'META',
        'JPM', 'GS', 'BAC', 'JNJ', 'PFE', 'UNH', 'LLY',
        'AMZN', 'DIS', 'HD', 'COST', 'DE', 'GE', 'XOM', 'CVX',
        'DAL', 'EXPE', 'SPY', 'QQQ', 'XLK', 'XLF', 'SHOP', 'NET', 'ZS', 'SCHW', 'PYPL',
        'MRK', 'BMY', 'ABBV', 'TMO', 'IBB',
        'TGT', 'WMT', 'ULTA', 'MCD',
        'NOC', 'RTX', 'LMT', 'FCX',
        'IWM', 'XLV', 'XLE', 'ARKK',
        #'SQ'
    ]
    #tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD']


    finalPnL = 0
    all_trades = []
    open_positions = []

    for ticker in tickers:
        filename = os.path.join(data_dir, f"{ticker}.csv")

        if os.path.exists(filename):
            df = pd.read_csv(filename, index_col=0, parse_dates=True)
            print(f"✅ Loaded cached data for {ticker}")
        else:
            df = yf.download(ticker, start='2025-01-01', end='2025-06-24', auto_adjust=True)
            if df.empty:
                print(f"⚠️ No data for {ticker}, skipping.")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df.index.name = 'datetime'
            df.to_csv(filename)
            print(f"⬇️ Downloaded and cached data for {ticker}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)  # Flatten column names

        for col in ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df.dropna(inplace=True)

        if df.empty:
            print(f"⚠️ No data for {ticker}, skipping.")
            continue

        data = bt.feeds.PandasData(dataname=df, name=ticker)

        cerebro = bt.Cerebro()
        cerebro.addstrategy(RSISRSIStrategy)
        cerebro.adddata(data)
        cerebro.addsizer(FixedQtySizer, qty=1)
        cerebro.broker.set_coc(True)
        cerebro.broker.set_cash(10000)
        
        strategies = cerebro.run()
        strategy = strategies[0]

        if hasattr(strategy, 'trades_df'):
            all_trades.append(strategy.trades_df)
            dollar_pnl = strategy.trades_df['Dollar_PnL'].sum()
            finalPnL += dollar_pnl

        position = cerebro.broker.getposition(data)
        if position.size > 0:
            buy_info = strategy.buy_infos.get(ticker, {})
            open_positions.append({
                'Ticker': ticker,
                'Size': position.size,
                'Price': position.price,
                'Value': position.size * position.price,
                'Buy Date': buy_info.get('Buy Date'),
                'Buy Price': buy_info.get('Buy Price')
            })

        

    print(f"\n💰 Final Total PnL across all tickers: {finalPnL:.2f}")

    print("\n📈 Open positions summary:")
    for pos in open_positions:
        print(f"{pos['Ticker']} | Size: {pos['Size']:.4f} | Entry: {pos['Buy Date']} at ${pos['Buy Price']:.2f} | Current: ${pos['Price']:.2f} | Value: ${pos['Value']:.2f}")

    final_balance = 10000 + finalPnL
    print(f"\n💼 Final Cash Value: ${final_balance:.2f}")

    if all_trades:
        final_df = pd.concat(all_trades, ignore_index=True)
        final_df.to_csv("backtest_results.csv", index=False)
