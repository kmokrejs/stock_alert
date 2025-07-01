
import alpaca
import ta
import pandas as pd
import os
from datetime import ( date, datetime)
import time
from email_sender import send_email 
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import (
    LimitOrderRequest,
    MarketOrderRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    OrderType,
    QueryOrderStatus,
    TimeInForce,
)
from alpaca.trading.requests import GetOrdersRequest


DOLLARS_PER_TRADE = 100

API_KEY = os.environ["API_KEY_PAPER"]
SECRET_KEY = os.environ["SECRET_KEY_PAPER"]
BASE_URL = os.environ["BASE_URL_PAPER"]

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)  # Use paper trading


POSITIONS_CSV = "positions.csv"

def load_positions():
    if os.path.exists(POSITIONS_CSV):
        return pd.read_csv(POSITIONS_CSV, parse_dates=['date'], dayfirst=True)
    else:
        return pd.DataFrame(columns=[
            'ticker', 'date', 'close', 'entry_rsi', 'srsi', 'ma20', 'status', 'sell_price', 'gain_loss'
        ])

def save_positions(positions_df):
    positions_df.to_csv(POSITIONS_CSV, index=False)


def place_bracket_order(ticker, entry_price):
    tp = round(entry_price * 1.20, 2)
    sl = round(entry_price * 0.80, 2)

    market_buy = MarketOrderRequest(
        symbol=ticker,
        notional=DOLLARS_PER_TRADE,
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,       
    )

    try:
        order = trading_client.submit_order(market_buy)
        print(f"🛒 Buy order submitted for {ticker} (${DOLLARS_PER_TRADE})")
        order_id = order.id
        for _ in range(10):
            fetched = trading_client.get_order_by_id(order_id)
            if fetched.filled_qty and float(fetched.filled_qty) > 0:
                filled_qty = float(fetched.filled_qty)
                print(f"✅ Order filled: {filled_qty} shares of {ticker}")
                break
            time.sleep(2)
        else:
            print("⚠️ Order not filled in time")
            return
        
        limit_tp_sell = LimitOrderRequest(
            symbol=ticker,
            qty=filled_qty,
            limit_price=tp,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        )
        trading_client.submit_order(limit_tp_sell)
        print(f"📈 Take Profit order placed at ${tp}")

        limit_sl_sell = StopOrderRequest(
            symbol=ticker,
            qty=filled_qty,
            stop_price=sl,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        )
        trading_client.submit_order(limit_sl_sell)
        print(f"🛑 Stop Loss order placed at ${sl}")
    except Exception as e:
        print(f"❌ Failed to execute trade for {ticker}: {e}")

def place_sell_order(ticker, qty):
    order = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC
    )

    try:
        response = trading_client.submit_order(order)
        print(f"💰 Sell order placed for {ticker} — Qty: {qty}")
        return response
    except Exception as e:
        print(f"❌ Failed to place sell order for {ticker}: {e}")
        return None

def fetch_data(ticker, start_date, end_date):
    request_params = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Day,
        start=start_date,
        end=end_date
    )
    bars = client.get_stock_bars(request_params).df

    if bars is None or bars.empty:
        print(f"⚠️ No data found for {ticker}")
        return None

    bars = bars[['open', 'high', 'low', 'close', 'volume']]
    bars.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    bars.index.name = 'datetime'
    return bars

def check_buy_signal(df):
    df = df.dropna()
    if df.empty:
        return False, {}

    latest = df.iloc[-1]
    close = latest['Close']
    rsi = latest['RSI']
    srsi = latest['SRSI']
    ma20 = latest['MA20']

    # BUY condition
    if rsi < 30 and srsi < 30 and close < ma20:
        return True, {
            'date': latest.name[1] if isinstance(latest.name, tuple) else latest.name,
            'close': close,
            'entry_rsi': rsi,
            'srsi': srsi,
            'ma20': ma20
        }
    return False, {}

def check_sell_signal(df, entry_rsi):
    df = df.dropna()
    if df.empty:
        return False, {}

    latest = df.iloc[-1]
    close = latest['Close']
    rsi = latest['RSI']
    srsi = latest['SRSI']
    ma20 = latest['MA20']
    ma50 = latest['MA50']

    rsi_jump = rsi - entry_rsi
    price_vs_ma20 = (close - ma20) / ma20 * 100
    price_vs_ma50 = (close - ma50) / ma50 * 100

    reasons = []
    if rsi > 70: reasons.append("RSI > 70")
    if srsi > 80: reasons.append("SRSI > 80")
    if rsi_jump > 42: reasons.append("RSI Jump > 42")
    if price_vs_ma20 > 12: reasons.append("Price > MA20")
    if price_vs_ma50 > 10: reasons.append("Price > MA50")

    if reasons:
        return True, {
            'date': latest.name[1] if isinstance(latest.name, tuple) else latest.name,
            'close': close,
            'rsi': rsi,
            'srsi': srsi,
            'ma20': ma20,
            'ma50': ma50,
            'rsi_jump': rsi_jump,
            'price_vs_ma20': price_vs_ma20,
            'price_vs_ma50': price_vs_ma50,
            'reasons': reasons
        }

    return False, {}

def sync_positions_with_alpaca():
    print("🔄 Syncing open positions with Alpaca...")

    # Load open positions
    positions_df = load_positions()
    open_positions = positions_df[positions_df['status'] == 'open']

    if open_positions.empty:
        print("✅ No open positions to sync.")
        return
    
    order_filter = GetOrdersRequest(status=QueryOrderStatus.ALL)
    all_orders = trading_client.get_orders(order_filter)


    updated = False

    for _, row in open_positions.iterrows():
        ticker = row['ticker']
        buy_price = float(row['close'])

        # Find any filled SELL order for this ticker
        for order in all_orders:
            if (
                order.symbol == ticker and
                order.side == OrderSide.SELL and
                order.filled_at is not None
            ):
                sell_price = float(order.filled_avg_price)
                gain_loss = round((sell_price - buy_price) / buy_price * 100, 2)

                # Update the DataFrame
                positions_df.loc[
                    (positions_df['ticker'] == ticker) & (positions_df['status'] == 'open'),
                    ['status', 'sell_price', 'gain_loss']
                ] = ['closed', sell_price, gain_loss]

                updated = True
                print(f"✅ {ticker}: SELL order filled at ${sell_price:.2f}, Gain/Loss: {gain_loss}%")

                # Cancel all remaining open orders for this symbol (e.g. SL)
                cancel_open_orders_for_symbol(ticker)

                break

    if updated:
        save_positions(positions_df)
        print("💾 Updated positions.csv with closed trades.")
    else:
        print("🕵️ No filled SELL orders found.")


def cancel_open_orders_for_symbol(ticker):
    open_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
    open_orders = trading_client.get_orders(open_filter)

    for order in open_orders:
        try:
            trading_client.cancel_order_by_id(order.id)
            print(f"🚫 Canceled open order for {ticker} (ID: {order.id})")
        except Exception as e:
            print(f"❌ Failed to cancel order for {ticker}: {e}")


def send_trade_summary_email():
    if buy_signals or watchlist:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        subject = f"📈 Trading Summary — {timestamp}"
        body_lines = []

        if buy_signals:
            body_lines.append("🟢 <b>New Buy Orders:</b><br>")
            for ticker, info in buy_signals:
                body_lines.append(
                    f"- {ticker}: ${info['close']:.2f} (RSI: {info['entry_rsi']:.2f}, SRSI: {info['srsi']:.2f}, MA20: {info['ma20']:.2f})<br>"
                )
            body_lines.append("<br>")

        if watchlist:
            body_lines.append("🔴 <b>Sell Alerts (Executed):</b><br>")
            for ticker, info in watchlist:
                gain_loss = round((info['close'] - positions[ticker]['close']) / positions[ticker]['close'] * 100, 2)
                reasons = ", ".join(info['reasons'])
                body_lines.append(
                    f"- {ticker}: ${info['close']:.2f} — Gain/Loss: {gain_loss}%<br>"
                    f"  Reasons: {reasons}<br>"
                )

    send_email(
        subject=subject,
        body="".join(body_lines),
        recipient_email=os.environ["EMAIL_RECIPIENT"],
        is_html=True
    )


def compute_indicators(df):
    if df is None or df.empty:
        return None
    try:
        df = df.copy()
        df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
        df['SRSI'] = ta.momentum.StochRSIIndicator(df['Close']).stochrsi_k()
        df['MA20'] = ta.trend.SMAIndicator(df['Close'], window=20).sma_indicator()
        df['MA50'] = ta.trend.SMAIndicator(df['Close'], window=50).sma_indicator()
        return df
    except Exception as e:
        print(f"❌ Failed to compute indicators: {e}")
        return None


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

start_date = "2025-01-01"
end_date = date.today().isoformat()

sync_positions_with_alpaca()

buy_signals = []
positions_df = load_positions()
held_tickers = set(positions_df[positions_df['status'] == 'open']['ticker'].unique())

watchlist = []
positions = {
    row['ticker']: {
        'entry_rsi': row['entry_rsi'],
        'date': row['date'],
        'close': row['close'],
        'srsi': row['srsi'],
        'ma20': row['ma20']
    }
    for _, row in positions_df.iterrows()
}

for ticker in tickers:
    df = fetch_data(ticker, start_date, end_date)
    if df is None:
        continue

    df = compute_indicators(df)
    if df is None:
        continue

    # ✅ Check buy condition
    buy_signal, buy_info = check_buy_signal(df)
    if buy_signal:
        if ticker in held_tickers:
          continue
        buy_info['ticker'] = ticker
        buy_info['status'] = 'open'
        buy_signals.append((ticker, buy_info))
        positions_df = pd.concat([positions_df, pd.DataFrame([buy_info])], ignore_index=True)
        entry_price = buy_info["close"]
        
        place_bracket_order(ticker, entry_price=entry_price)


save_positions(positions_df)

print("\n👁️ Watchlist (Sell Alerts from Positions):")
for ticker, entry in positions.items():
    df = fetch_data(ticker, start_date, end_date)
    if df is None:
        continue
    df = compute_indicators(df)
    if df is None:
        continue

    sell_signal, sell_info = check_sell_signal(df, entry['entry_rsi'])
    if sell_signal:
      watchlist.append((ticker, sell_info))
      print(f"🔴 {ticker} — SELL signal on {sell_info['date'].date()} @ ${sell_info['close']:.2f}")
      print(f"Reasons: {', '.join(sell_info['reasons'])}")

      # 🛑 Place a real sell order
      place_sell_order(ticker, qty=1)

      # ✅ Compute gain/loss
      sell_price = sell_info['close']
      buy_price = float(entry['close'])
      gain_loss = round((sell_price - buy_price) / buy_price * 100, 2)

      # ⛔️ Update trade status and log results
      positions_df.loc[
          (positions_df['ticker'] == ticker) & (positions_df['status'] == 'open'),
          ['status', 'sell_price', 'gain_loss']
      ] = ['closed', sell_price, gain_loss]

      print(f"📤 Trade closed for {ticker} — Sold at ${sell_price:.2f}, Gain/Loss: {gain_loss}%")

save_positions(positions_df)

print("\n🧾 Buy Signals Summary:")
for ticker, info in buy_signals:
    print(f"🟢 {ticker} — Buy on {info['date'].date()} @ ${info['close']:.2f} (RSI: {info['entry_rsi']:.2f}, SRSI: {info['srsi']:.2f})")

print("\n📉 Sell Watchlist Summary:")
if not watchlist:
    print("No sell signals triggered.")
else:
    for ticker, info in watchlist:
      print(f"🔴 {ticker} — Sell on {info['date'].date()} @ ${info['close']:.2f} "
      f"(Reasons: {', '.join(info['reasons'])}, Gain/Loss: {gain_loss}%)")

send_trade_summary_email()