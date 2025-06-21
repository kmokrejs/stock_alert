import yfinance as yf
import pandas as pd
from email_sender import send_email
from dotenv import load_dotenv
import numpy as np
from datetime import datetime
import os
load_dotenv()


def compute_rsi(series, window=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_srsi(rsi, window=14):
    min_rsi = rsi.rolling(window).min()
    max_rsi = rsi.rolling(window).max()
    range_rsi = max_rsi - min_rsi
    srsi = (rsi - min_rsi) / range_rsi.replace(0, pd.NA)
    return srsi * 100

def analyze_entry(rsi, srsi, price_vs_ma20, price_vs_ma50, pe_ratio, html_format=False):
    # Base RSI/SRSI logic
    if rsi < 30 and srsi < 20:
        base_signal = "🔥 Strong Buy"
    elif rsi < 35 and srsi < 30:
        base_signal = "✅ Buy"
    elif 35 <= rsi <= 50 and srsi < 50:
        base_signal = "🤔 Watch (Neutral)"
    elif rsi > 70 or srsi > 80:
        base_signal = "⚠️ Overbought — Consider Selling"
    else:
        base_signal = "Hold"

    # Add-on adjustments:
    notes = []

    if price_vs_ma20 < -5 or price_vs_ma50 < -5:
        notes.append("📉 Price below MA — possible undervaluation")
    if price_vs_ma20 > 5 or price_vs_ma50 > 5:
        notes.append("📈 Price above MA — watch for overbought")

    if pe_ratio and pe_ratio < 15:
        notes.append("💰 Low P/E — undervalued?")
    elif pe_ratio and pe_ratio > 30:
        notes.append("🧨 High P/E — priced for perfection")

    # Combine
    if notes:
        separator = "<br>" if html_format else "\n"
        return f"{base_signal}{separator}" + separator.join(notes)
    else:
        return base_signal
    
def log_trade_opportunity(data, filename="trade_log.csv"):
    log_cols = [
        'Date', 'Ticker', 'Price', 'RSI', 'SRSI',
        'MA20', 'MA50',
        'Price_vs_MA20(%)', 'Price_vs_MA50(%)',
        'PE_Ratio', 'Recommendation', 'Target1', 'Target2', 'StopLoss'
    ]

    entry = {
        **data,
        'Target1': round(data['MA20'], 2),
        'Target2': round(data['MA50'], 2),
        'StopLoss': round(data['Price'] * 0.975, 2)
    }

    df = pd.DataFrame([entry], columns=log_cols)

    if os.path.exists(filename):
        df.to_csv(filename, mode='a', index=False, header=False)
    else:
        df.to_csv(filename, mode='w', index=False, header=True)



def analyze_ticker(ticker):
    start_date = (pd.Timestamp.today() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')
    end_date = pd.Timestamp.today().strftime('%Y-%m-%d')
    
    df = yf.download(ticker, start=start_date, end=end_date)[['Close']].copy()
    df.dropna(inplace=True)
    df.reset_index(inplace=True)
    df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    df['Date'] = pd.to_datetime(df['Date'])

    df['RSI'] = compute_rsi(df['Close'])
    df['SRSI'] = compute_srsi(df['RSI'])
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df.dropna(subset=['RSI', 'SRSI', 'MA20', 'MA50'], inplace=True)

    latest = df.iloc[-1]

    try:
        info = yf.Ticker(ticker).info
        pe_ratio = info.get('trailingPE', None)
    except Exception:
        pe_ratio = None

    try:
        current_price = yf.Ticker(ticker).fast_info['last_price']
    except Exception:
        current_price = latest['Close']  

    recommendation = analyze_entry(
        latest['RSI'],
        latest['SRSI'],
        (current_price - latest['MA20']) / latest['MA20'] * 100,
        (current_price - latest['MA50']) / latest['MA50'] * 100,
        pe_ratio,
        html_format=True
    )

    return {
        'Ticker': ticker,
        'Date': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'Price': current_price,
        'RSI': latest['RSI'],
        'SRSI': latest['SRSI'],
        'MA20': latest['MA20'],
        'MA50': latest['MA50'],
        'Price_vs_MA20(%)': (current_price - latest['MA20']) / latest['MA20'] * 100,
        'Price_vs_MA50(%)': (current_price - latest['MA50']) / latest['MA50'] * 100,
        'PE_Ratio': pe_ratio,
        'Recommendation': recommendation
    }



# === Run analysis on desired tickers ===

if __name__ == "__main__":
    tickers = [
    'AAPL', 'MSFT', 'NVDA', 'AMD', 'GOOGL', 'META', 'TSLA',
    'JPM', 'GS', 'BAC', 'JNJ', 'PFE', 'UNH', 'LLY',
    'AMZN', 'DIS', 'HD', 'COST', 'NKE',
    'CAT', 'DE', 'GE', 'XOM', 'CVX',
    'DAL', 'UBER', 'EXPE', 'SPY', 'QQQ', 'XLK', 'XLF',
    'CRM', 'SHOP', 'NET', 'ZS', 'SQ', 'DOCN', 'PLTR',
    'COIN', 'SOFI', 'SCHW', 'PYPL',
    'MRK', 'BMY', 'ABBV', 'TMO', 'IBB',
    'TGT', 'WMT', 'ULTA', 'SBUX', 'MCD',
    'ABNB', 'BKNG', 'MAR', 'LYFT',
    'NOC', 'RTX', 'LMT', 'FCX',
    'IWM', 'XLV', 'XLE', 'ARKK']
    watchlist = ['HD', 'MCD']
    results = []
    buy_opportunities = []


    for ticker in tickers:
        try:
            result = analyze_ticker(ticker)
            if result:
                results.append(result)

            if result['Recommendation'].startswith("🔥") or result['Recommendation'].startswith("✅"):
                trade_result = result.copy()
                trade_result['Target1'] = round(result['MA20'], 2)
                trade_result['Target2'] = round(result['MA50'], 2)
                trade_result['StopLoss'] = round(result['Price'] * 0.975, 2)

                buy_opportunities.append(trade_result) 
                log_trade_opportunity(trade_result)    
        except Exception as e:
            print(f"❌ Error analyzing {ticker}: {e}")
    
    watchlist_results = [r for r in results if r['Ticker'] in watchlist]
    if watchlist_results:
        watchlist_df = pd.DataFrame(watchlist_results)
        watchlist_html = watchlist_df[['Ticker', 'Price', 'RSI', 'SRSI', 'PE_Ratio', 'Recommendation']].to_html(index=False, justify='center', border=1, escape=False)
        watchlist_section = f"<h3>🔍 Watchlist</h3>{watchlist_html}"
    else:
        watchlist_section = "<p>No watchlist data available.</p>"

    if results:
        df = pd.DataFrame(results)

        summary = "\n".join([
            f"{r['Ticker']}: {r['Recommendation']} | RSI: {r['RSI']:.2f}, SRSI: {r['SRSI']:.2f}"
            for r in results
        ])

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")


        html_table = df.to_html(index=False, justify='center', border=1, escape=False)

        if buy_opportunities:
            buys_df = pd.DataFrame(buy_opportunities)
            buys_html = buys_df[['Ticker', 'Price', 'RSI', 'SRSI', 'PE_Ratio', 'Recommendation', 'Target1', 'Target2', 'StopLoss']].to_html(index=False, justify='center', border=1, escape=False)
            trades_section = f"<h3>💸 Trade Opportunities</h3>{buys_html}"
        else:
            trades_section = "<p>No trade opportunities today.</p>"


        html_body = f"""
        <html>
        <head>
            <style>
                table {{
                    border-collapse: collapse;
                    width: 100%;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: center;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
            </style>
        </head>
        <body>
            <h2>📈 Daily Stock Analysis</h2>
            {watchlist_section}
            <br>
            {html_table}
            <br>
            {trades_section}    
        </body>
        </html>
        """

        send_email(
            subject = f"📊 Daily Stock Report — {timestamp}",
            body=html_body,
            recipient_email=os.environ["EMAIL_RECIPIENT"],
            is_html=True
        )
        print("✅ Email sent.")
    else:
        print("❌ No analysis results to send.")
