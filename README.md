# AI Stock Strategy Backtester

A web application that allows users to describe trading strategies in natural language and see backtesting results.

## Features

- Natural language trading strategy input
- AI-powered code generation using OpenAI
- Backtesting on Nifty 500 stocks
- Interactive results with key performance metrics
- Beautiful visualizations of portfolio value and drawdowns

## Requirements

- Python 3.8+
- OpenAI API key

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Install the required packages:
```bash
pip install -r requirements.txt
```

3. Ensure you have the Nifty 500 stocks CSV file (`ind_nifty500list.csv`) in the root directory.

## Usage

1. Start the Flask server:
```bash
python app.py
```

2. Open your web browser and navigate to:
```
http://127.0.0.1:5000/
```

3. Enter your trading strategy in plain English
4. Provide your OpenAI API key
5. Adjust initial capital and position size if needed
6. Click "Run Backtest" and wait for results

## Example Strategies

Try these example strategies:

- "If a stock hits its 52-week high, buy it. Use a 10% stop loss and exit with a 15% profit target."
- "Buy when a stock's 50-day moving average crosses above its 200-day moving average. Sell when it crosses below."
- "Buy stocks with RSI below 30 (oversold) and sell when RSI goes above 70 (overbought)."

## Technology Stack

- **Backend**: Flask, Python
- **Data Processing**: Pandas, NumPy, vectorbt
- **Market Data**: yfinance
- **Frontend**: HTML, CSS, JavaScript, Bootstrap 5
- **AI**: OpenAI API

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This application is for educational purposes only. Past performance is not indicative of future results. Always do your own research before making investment decisions. 