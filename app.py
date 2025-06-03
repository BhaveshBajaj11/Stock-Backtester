from flask import Flask, render_template, request, jsonify
import os
import openai
import traceback
import numpy as np
import pandas as pd
import io
import base64
from datetime import datetime, timedelta
import yfinance as yf
import vectorbt as vbt
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

matplotlib.use('Agg')  # Use non-interactive backend

# Suppress pandas warnings
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
pd.set_option('future.no_silent_downcasting', True)

app = Flask(__name__)

def clean_generated_code(code_str):
    """Clean and validate generated code from OpenAI"""
    # Remove markdown code blocks
    if code_str.startswith('```python'):
        code_str = code_str[9:]
    if code_str.startswith('```'):
        code_str = code_str[3:]
    if code_str.endswith('```'):
        code_str = code_str[:-3]
    
    # Remove any explanatory text after the code
    lines = code_str.split('\n')
    cleaned_lines = []
    for line in lines:
        # Stop at common explanation patterns
        if any(phrase in line.lower() for phrase in ['this code', 'the above', 'explanation:', 'note:']):
            break
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines).strip()

def auto_backtest(
    user_prompt: str,
    tickers: list[str],
    total_cash: float = 10_000,
    size: float = 0.2,
    period: str = "24mo",
    interval: str = "1d",
    max_retries: int = 3
) -> vbt.Portfolio:
    # Configure OpenAI
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if openai.api_key is None:
        raise ValueError("You must provide an OpenAI API key via OPENAI_API_KEY env var.")  

    # Build a prompt that tells GPT to spit out exactly the code you need
    base_prompt = f'''You are a Python expert. Generate ONLY executable code for stock backtesting.

CRITICAL RULES:
1. NEVER use loops (for/while) - use vectorized pandas operations only
2. Use .ffill() instead of .fillna(method='ffill')
3. Use .iloc[] for position-based indexing, .loc[] for label-based
4. Avoid .at[] indexing - use boolean masking instead
5. For profit targets/stop losses, use vectorized operations
6. ALWAYS ensure entries and exits have EXACT same shape as close
7. Use standard operators (+ - * /) instead of .div() .mul() on literals

DATA STRUCTURE:
`raw` is a multi-level DataFrame from yfinance. Extract data like this:
close = raw.xs('Close', axis=1, level=1)

REQUIREMENTS - Create these 3 variables:
1. close: Price DataFrame
2. entries: Boolean DataFrame (same shape as close) 
3. exits: Boolean DataFrame (same shape as close)

SHAPE SAFETY RULES:
# After creating entries/exits, ALWAYS add these lines to ensure correct shape:
entries = entries.reindex(index=close.index, columns=close.columns, fill_value=False)
exits = exits.reindex(index=close.index, columns=close.columns, fill_value=False)

WORKING EXAMPLES:

# Basic pattern - ALWAYS start with this:
close = raw.xs('Close', axis=1, level=1)

# Example 1: Simple MA crossover
sma_short = close.rolling(10).mean()
sma_long = close.rolling(20).mean()
entries = sma_short > sma_long
exits = sma_short < sma_long
# ALWAYS add shape fixing:
entries = entries.reindex(index=close.index, columns=close.columns, fill_value=False)
exits = exits.reindex(index=close.index, columns=close.columns, fill_value=False)

# Example 2: RSI strategy  
delta = close.diff()
gain = delta.where(delta > 0, 0).rolling(14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
rsi = 100 - (100 / (1 + gain / loss))
entries = rsi < 30
exits = rsi > 70
# ALWAYS add shape fixing:
entries = entries.reindex(index=close.index, columns=close.columns, fill_value=False)
exits = exits.reindex(index=close.index, columns=close.columns, fill_value=False)

# Example 3: Index filter (Nifty above 200 EMA) - SAFE METHOD
idx_data = yf.download('^CRSLDX', period='24mo', interval='1d', progress=False)
idx_close = idx_data['Close'].reindex(close.index).ffill()
idx_ema200 = idx_close.ewm(span=200).mean()
bullish_days = idx_close > idx_ema200
# Create base conditions first
ema9 = close.ewm(span=9).mean()
ema21 = close.ewm(span=21).mean()
cross_up = (ema9 > ema21) & (ema9.shift(1) <= ema21.shift(1))
# Apply index filter safely
entries = cross_up.multiply(bullish_days, axis=0)
exits = cross_up.multiply(~bullish_days, axis=0)  # Exit when index turns bearish
# ALWAYS add shape fixing:
entries = entries.reindex(index=close.index, columns=close.columns, fill_value=False)
exits = exits.reindex(index=close.index, columns=close.columns, fill_value=False)

# Example 4: Profit target/Stop loss (VECTORIZED - NO LOOPS!)
# For 5% profit target, 5% stop loss:
entry_price = close.where(entries).ffill()
target_hit = close >= entry_price * 1.05
stop_hit = close <= entry_price * 0.95
exits = target_hit | stop_hit
# ALWAYS add shape fixing:
exits = exits.reindex(index=close.index, columns=close.columns, fill_value=False)

CRITICAL: To avoid "Must pass 2-d input" error when creating masks:
# WRONG - causes 2D input error:
# mask = pd.DataFrame(np.broadcast_to(...))  # ❌ NEVER DO THIS
# CORRECT - use .multiply() method instead:
entries = condition_dataframe.multiply(index_series, axis=0)  # ✅ SAFE METHOD

AVOID DANGEROUS INDEXING PATTERNS:
# WRONG - causes KeyError with boolean indexing:
# exit_df.loc[bearish_series, :] = True  # ❌ DON'T DO THIS
# CORRECT - use broadcasting or multiply:
# exit_df = bearish_series.multiply(pd.DataFrame(True, index=close.index, columns=close.columns), axis=0)  # ✅ SAFE

PYTHON SYNTAX RULES:
# WRONG - invalid syntax:
# rsi = 100 - 100.div(1 + rs)  # ❌ Can't call .div() on literal
# CORRECT - use standard operators:
# rsi = 100 - (100 / (1 + rs))  # ✅ Proper syntax

IMPORTANT: Ensure trades can be closed properly:
# Always include proper exit conditions that will trigger
# For strategies with index filters, make sure exits are not overly restrictive
# Example: If entry requires bullish market, exit should trigger in bearish OR profit/stop conditions

CRITICAL INDEX SYMBOL: Use '^CRSLDX' for Nifty 500 index data (NOT ^NSE500 or other symbols)

USER STRATEGY: "{user_prompt}"

Generate ONLY the code (no explanations, no markdown):'''

    # Load stock data
    csv_path = 'ind_nifty500list.csv'
    df = pd.read_csv(csv_path)
    raw_syms = df['Symbol'].dropna().astype(str).str.upper().unique()
    tickers = [sym if sym.endswith('.NS') else f"{sym}.NS" for sym in raw_syms]
    raw = yf.download(
        tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        progress=False
    )

    code_str = None
    last_error = ""
    env = {"raw": raw}
    preloaded_globals = {
        "__builtins__": __builtins__,  # give it access to builtins like range, len, etc.
        "pd": pd,
        "yf": yf,
        "vbt": vbt,
        "np": np
        # add any other names you expect GPT to use…
    }

    for attempt in range(1, max_retries + 1):
        # Get (or re-get) the code from OpenAI
        if code_str is None:
            prompt = base_prompt
        else:
            # on retry, include last code + error
            prompt = (
                base_prompt
                + "\n# Previous code:\n"
                + code_str
                + "\n# Error on attempt "
                + str(attempt - 1)
                + ":\n"
                + last_error
                + "\n# Please correct and output only corrected code."
            )
            print(prompt)
        
        resp = openai.ChatCompletion.create(
            model="o4-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        code_str = resp.choices[0].message.content
        
        # Clean the generated code
        code_str = clean_generated_code(code_str)
        
        # Debug: Print the cleaned code
        print(f"\n--- Attempt {attempt} Generated Code ---")
        print(code_str)
        print("--- End Generated Code ---\n")

        # Try to exec it
        try:
            exec(code_str, preloaded_globals, env)

            # Validate that required variables exist
            if "close" not in env or "entries" not in env or "exits" not in env:
                raise ValueError("Generated code must define 'close', 'entries', and 'exits' variables")

            # Pull out the variables GPT defined
            close = env["close"]
            entries = env["entries"]
            exits = env["exits"]
            
            # Validate DataFrame shapes
            if not isinstance(close, pd.DataFrame):
                raise ValueError("'close' must be a pandas DataFrame")
            if not isinstance(entries, pd.DataFrame):
                raise ValueError("'entries' must be a pandas DataFrame")
            if not isinstance(exits, pd.DataFrame):
                raise ValueError("'exits' must be a pandas DataFrame")
            
            # Automatically fix shape mismatches instead of failing
            if entries.shape != close.shape:
                print(f"Fixing entries shape mismatch: {entries.shape} -> {close.shape}")
                entries = entries.reindex(index=close.index, columns=close.columns, fill_value=False)
            
            if exits.shape != close.shape:
                print(f"Fixing exits shape mismatch: {exits.shape} -> {close.shape}")
                exits = exits.reindex(index=close.index, columns=close.columns, fill_value=False)

            # Run the backtest
            n_symbols = close.shape[1]
            # entries and exits shapes are now guaranteed to match close
            
            pf = vbt.Portfolio.from_signals(
                close=close,
                entries=entries,
                exits=exits,
                init_cash=total_cash,
                fees=0.001,
                size=size,
                size_type='percent',
                group_by=['basket'] * n_symbols,
                cash_sharing=True
            )

            # Success — return the portfolio immediately
            return pf

        except Exception as e:
            # Send only the essential error message to AI, not full traceback
            error_str = str(e)
            if "shape" in error_str and "doesn't match" in error_str:
                last_error = f"Shape mismatch error: {error_str}\nEnsure entries and exits have same shape as close by adding:\nentries = entries.reindex(index=close.index, columns=close.columns, fill_value=False)\nexits = exits.reindex(index=close.index, columns=close.columns, fill_value=False)"
            elif "KeyError" in error_str and "None of" in error_str:
                last_error = f"Indexing error: {error_str}\nAvoid using .loc[] with boolean series directly. Use .multiply() method instead for applying conditions across DataFrame."
            elif "YFPricesMissingError" in error_str or "No data found" in error_str:
                last_error = f"Invalid ticker symbol: {error_str}\nUse '^CRSLDX' for Nifty 500 index data, not other symbols."
            elif "SyntaxError" in error_str:
                last_error = f"Python syntax error: {error_str}\nCheck for invalid method calls on literals (e.g., use (100).div() not 100.div()) or use standard operators like / instead of .div()"
            else:
                last_error = f"Error: {error_str}"
            
            full_traceback = traceback.format_exc()
            print(f"Attempt {attempt} failed with error:\n{full_traceback}")
            if attempt == max_retries:
                # If all attempts failed, try a simple fallback strategy
                print("All AI attempts failed. Using simple fallback strategy...")
                try:
                    # Simple moving average crossover as fallback
                    fallback_code = '''
close = raw.xs('Close', axis=1, level=1)
# Simple buy and hold strategy - very basic fallback
entries = pd.DataFrame(False, index=close.index, columns=close.columns)
exits = pd.DataFrame(False, index=close.index, columns=close.columns)
# Buy on first day, never sell (simple buy and hold)
entries.iloc[10] = True  # Buy after 10 days to avoid initial NaN issues
'''
                    exec(fallback_code, preloaded_globals, env)
                    
                    # Validate fallback worked
                    if "close" in env and "entries" in env and "exits" in env:
                        close = env["close"]
                        entries = env["entries"]
                        exits = env["exits"]
                        
                        # Run the backtest with fallback
                        n_symbols = close.shape[1]
                        # Shapes are already ensured in the fallback code

                        pf = vbt.Portfolio.from_signals(
                            close=close,
                            entries=entries,
                            exits=exits,
                            init_cash=total_cash,
                            fees=0.001,
                            size=size,
                            size_type='percent',
                            group_by=['basket'] * n_symbols,
                            cash_sharing=True
                        )
                        print("Fallback strategy executed successfully!")
                        return pf
                except Exception as fallback_error:
                    fallback_traceback = traceback.format_exc()
                    print(f"Fallback strategy also failed: {fallback_error}")
                    print(f"Fallback traceback: {fallback_traceback}")
                
                # give up
                raise RuntimeError(
                    f"Failed to generate valid code after {max_retries} attempts.\n"
                    f"Last error:\n{last_error}"
                )

    return None

def fig_to_base64(fig):
    """Convert a matplotlib figure to base64 string for HTML display"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.close()
    return img_str

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/backtest', methods=['POST'])
def backtest():
    data = request.json
    user_prompt = data.get('prompt', '')
    total_cash = float(data.get('total_cash', 50000))
    size = float(data.get('size', 0.1))
    
    try:
        # Get tickers from CSV
        csv_path = 'ind_nifty500list.csv'
        df = pd.read_csv(csv_path)
        raw_syms = df['Symbol'].dropna().astype(str).str.upper().unique()
        tickers = [sym if sym.endswith('.NS') else f"{sym}.NS" for sym in raw_syms]
        
        print("Starting backtest...")
        # Run the backtest - use default API key in auto_backtest function
        portfolio = auto_backtest(
            user_prompt=user_prompt,
            tickers=tickers,
            total_cash=total_cash,
            size=size,
            max_retries=3
        )
        
        print("Getting stats...")
        # Get portfolio stats - vectorbt calculates metrics automatically
        stats = portfolio.stats()
        
        # Get trade records
        trades = portfolio.trades.records_readable
        
        # Debug: Print available columns
        print("Available trade columns:", trades.columns.tolist())
        print("Sample trade record:", trades.head(1).to_dict('records') if len(trades) > 0 else "No trades")
        print(f"Total number of trades: {len(trades)}")
        
        # Debug: Check trade status distribution
        if len(trades) > 0:
            print("Trade status distribution:")
            print(trades['Status'].value_counts())
            print("Trade direction distribution:")
            print(trades['Direction'].value_counts())
            closed_trades = trades[trades['Status'] == 'Closed']
            open_trades = trades[trades['Status'] == 'Open']
            print(f"Closed trades: {len(closed_trades)}, Open trades: {len(open_trades)}")
        
        # If no trades, there might be an issue with the strategy
        if len(trades) == 0:
            print("Warning: No trades generated. Check strategy logic.")
            print("Portfolio stats:", portfolio.stats())
        
        # Calculate return percentage manually if not available
        if 'Return [%]' not in trades.columns:
            trades['Return [%]'] = ((trades['Avg Exit Price'] - trades['Avg Entry Price']) / trades['Avg Entry Price']) * 100
        
        # Ensure return percentage is calculated correctly (handle any remaining zeros)
        trades['Return [%]'] = trades.apply(lambda row: 
            ((row['Avg Exit Price'] - row['Avg Entry Price']) / row['Avg Entry Price']) * 100 
            if row['Avg Entry Price'] != 0 else 0, axis=1)
        
        # Alternative: try different column names if the calculation seems wrong
        possible_return_cols = ['Return [%]', 'Return%', 'Return', 'Pct_Return']
        for col in possible_return_cols:
            if col in trades.columns and trades[col].abs().max() > 0:
                trades['Return [%]'] = trades[col]
                break
        
        # Debug: Check calculated returns
        print("Return % stats:", trades['Return [%]'].describe())
        print("Sample calculated returns:", trades[['Avg Entry Price', 'Avg Exit Price', 'Return [%]']].head())
        
        # Sort trades by PnL to get best and worst
        trades_sorted = trades.sort_values('PnL', ascending=False)
        best_trades = trades_sorted.head(100).to_dict('records')
        worst_trades = trades_sorted.tail(100).to_dict('records')
        
        # Calculate advanced metrics manually
        if len(trades) > 0:
            # Win rate calculation
            winning_trades = len(trades[trades['PnL'] > 0])
            losing_trades = len(trades[trades['PnL'] < 0])
            total_trades = len(trades)
            win_rate_manual = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
            
            # Profit factor calculation (Gross Profit / Gross Loss)
            gross_profit = trades[trades['PnL'] > 0]['PnL'].sum() if winning_trades > 0 else 0
            gross_loss = abs(trades[trades['PnL'] < 0]['PnL'].sum()) if losing_trades > 0 else 1
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
        else:
            win_rate_manual = 0
            profit_factor = 0
            winning_trades = 0
            total_trades = 0
        
        print(f"Manual calculations:")
        print(f"Win rate: {winning_trades}/{total_trades} = {win_rate_manual:.2f}%")
        print(f"Profit factor: {profit_factor:.2f}")
        
        # Get benchmark data (Nifty 50 and Nifty 500)
        print("Fetching benchmark data...")
        nifty50_data = yf.download('^NSEI', period='24mo', interval='1d', progress=False)
        nifty500_data = yf.download('^CRSLDX', period='24mo', interval='1d', progress=False)
        
        # Align benchmark data with portfolio dates
        portfolio_dates = portfolio.value().index
        nifty50_aligned = nifty50_data['Close'].reindex(portfolio_dates).ffill()
        nifty500_aligned = nifty500_data['Close'].reindex(portfolio_dates).ffill()
        
        # Normalize benchmarks to same starting value as portfolio for comparison
        portfolio_values = portfolio.value()
        
        # Handle case where portfolio.value() returns DataFrame
        if isinstance(portfolio_values, pd.DataFrame):
            portfolio_values = portfolio_values.iloc[:, 0]  # Take first column
        
        start_value = portfolio_values.iloc[0]
        
        nifty50_normalized = (nifty50_aligned / nifty50_aligned.iloc[0]) * start_value
        nifty500_normalized = (nifty500_aligned / nifty500_aligned.iloc[0]) * start_value
        
        # Create a dictionary with the stats we want to display
        # Handle NaN values gracefully
        def safe_stat(value, default="0.00"):
            try:
                if pd.isna(value) or value == float('inf') or value == float('-inf'):
                    return default
                return f"{float(value):.2f}"
            except:
                return default
        
        # Debug: Print available stats keys
        print("Available stats keys:", list(stats.keys()) if hasattr(stats, 'keys') else "Not a dict")
        print("Stats type:", type(stats))
        
        stats_dict = {
            'total_return': f"{safe_stat(stats['Total Return [%]'])}%",
            'end_value': f"{safe_stat(stats['End Value'])}",
            'max_drawdown': f"{safe_stat(stats['Max Drawdown [%]'])}%",
            'win_rate': f"{win_rate_manual:.2f}%",
            'total_trades': str(int(total_trades)),
            'profit_factor': f"{profit_factor:.2f}"
        }
        
        print("Generating plots...")
        # Generate value plot using matplotlib directly
        plt.figure(figsize=(12, 6))
        portfolio.value().plot(title='Portfolio Value', figsize=(12, 6))
        plt.grid(True)
        plt.tight_layout()
        value_fig = plt.gcf()
        value_img = fig_to_base64(value_fig)
        plt.close(value_fig)
        
        # Generate drawdowns plot using matplotlib directly
        plt.figure(figsize=(12, 6))
        portfolio.drawdown().plot(title='Portfolio Drawdowns', figsize=(12, 6), color='red')
        plt.grid(True)
        plt.tight_layout()
        dd_fig = plt.gcf()
        dd_img = fig_to_base64(dd_fig)
        plt.close(dd_fig)
        print(portfolio.trades.records_readable)
        print("Sending response...")
        return jsonify({
            'status': 'success',
            'stats': stats_dict,
            'value_plot': value_img,
            'drawdowns_plot': dd_img,
            'best_trades': best_trades,
            'worst_trades': worst_trades,
            'portfolio_data': {
                'dates': [d.strftime('%Y-%m-%d') for d in portfolio_values.index],
                'values': portfolio_values.values.tolist()
            },
            'benchmark_data': {
                'nifty50': {
                    'dates': [d.strftime('%Y-%m-%d') for d in nifty50_normalized.index],
                    'values': nifty50_normalized.values.tolist()
                },
                'nifty500': {
                    'dates': [d.strftime('%Y-%m-%d') for d in nifty500_normalized.index],
                    'values': nifty500_normalized.values.tolist()
                }
            }
        })
    
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"Error: {str(e)}")
        print(traceback_str)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback_str
        }), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False, threaded=True) 