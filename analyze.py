from src.analysis import analyze_ticker
from src.email_sender import send_email
import os
import pandas as pd

tickers = ['AAPL', 'MSFT', 'V', 'GOOGL']
results = []

for ticker in tickers:
    try:
        result = analyze_ticker(ticker)
        results.append(result)
    except Exception as e:
        print(f"❌ Error analyzing {ticker}: {e}")

df = pd.DataFrame(results)
csv_path = "daily_analysis.csv"
df.to_csv(csv_path, index=False)

summary = "\n".join([
    f"{r['Ticker']}: {r['Recommendation']} | RSI: {r['RSI']:.2f}, SRSI: {r['SRSI']:.2f}"
    for r in results
])

recipient = os.environ['EMAIL_RECIPIENT']

send_email(
    subject="📈 Daily Stock Alert",
    body=f"Here is your daily stock analysis:\n\n{summary}",
    recipient_email=recipient, 
    attachment_path=csv_path
)
