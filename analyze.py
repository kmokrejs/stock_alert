import yfinance as yf
import pandas as pd
from email_sender import send_email
from dotenv import load_dotenv
import numpy as np
import os
load_dotenv()


def compute_rsi(series, window=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_srsi(rsi, window=14):
    min_rsi = rsi.rolling(window).min()
    max_rsi = rsi.rolling(window).max()
    range_rsi = max_rsi - min_rsi
    srsi = (rsi - min_rsi) / range_rsi.replace(0, pd.NA)
    return srsi * 100

def analyze_entry(rsi, srsi):
    if rsi < 30 and srsi < 20:
        return "🔥 Strong Buy"
    elif rsi < 35 and srsi < 30:
        return "✅ Buy"
    elif 35 <= rsi <= 50 and srsi < 50:
        return "🤔 Watch (Neutral)"
    elif rsi > 70 or srsi > 80:
        return "⚠️ Overbought — Consider Selling"
    else:
        return "Hold"

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
    df.dropna(subset=['RSI', 'SRSI'], inplace=True)

    latest = df.iloc[-1]
    recommendation = analyze_entry(latest['RSI'], latest['SRSI'])

    return {
        'Ticker': ticker,
        'Date': latest['Date'].date(),
        'Price': latest['Close'],
        'RSI': latest['RSI'],
        'SRSI': latest['SRSI'],
        'Recommendation': recommendation
    }

# === Run analysis on desired tickers ===

if __name__ == "__main__":
    tickers = ['MSFT', 'NVDA','AAPL', 'V', 'GOOGL', 'META', 'JNJ', 'F', 'EXPE']
    results = []

    for ticker in tickers:
        try:
            result = analyze_ticker(ticker)
            if result:
                results.append(result)
        except Exception as e:
            print(f"❌ Error analyzing {ticker}: {e}")

    if results:
        df = pd.DataFrame(results)
        csv_path = "daily_stock_report.csv"
        df.to_csv(csv_path, index=False)

        summary = "\n".join([
            f"{r['Ticker']}: {r['Recommendation']} | RSI: {r['RSI']:.2f}, SRSI: {r['SRSI']:.2f}"
            for r in results
        ])

        recipient = os.environ['EMAIL_RECIPIENT']

        html_table = df.to_html(index=False, justify='center', border=1)

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
            {html_table}
        </body>
        </html>
        """

        send_email(
            subject="📊 Daily Stock Report",
            body=html_body,
            recipient_email=os.environ["EMAIL_RECIPIENT"],
            attachment_path=csv_path,
            is_html=True
        )
        print("✅ Email sent with CSV attachment.")
    else:
        print("❌ No analysis results to send.")
