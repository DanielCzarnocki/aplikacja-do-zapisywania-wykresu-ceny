import logging
import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from backend.database import engine, Base, get_db, SessionLocal
from backend.models import Candle, TradeHistory, StrategyState
import json
from sqlalchemy import func, desc
from backend.fetcher import fetch_and_store_candles, backfill_missing_candles
from backend.strategy import apply_strategy_ms
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

scheduler = BackgroundScheduler()

import subprocess
import threading
from contextlib import asynccontextmanager

bot_process = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_process
    logger.info("Starting up and initializing scheduler...")
    # Run once immediately
    fetch_and_store_candles()
    
    # Start the historical backfill in a separate background thread
    backfill_thread = threading.Thread(target=backfill_missing_candles, daemon=True)
    backfill_thread.start()
    logger.info("Background historical backfill process started.")
    
    # Start the strategy DB daemon
    strategy_thread = threading.Thread(target=strategy_state_daemon, daemon=True)
    strategy_thread.start()
    logger.info("Stateful strategy daemon started.")
    
    # Start the browser bot subprocess
    try:
        bot_process = subprocess.Popen(["python", os.path.join("backend", "browser_bot.py")])
        logger.info("Browser bot subprocess started.")
    except Exception as e:
        logger.error(f"Failed to start browser bot subprocess: {e}")
    
    # Schedule to run every 5 seconds
    scheduler.add_job(fetch_and_store_candles, 'interval', seconds=5)
    scheduler.start()
    
    yield
    
    logger.info("Shutting down scheduler...")
    scheduler.shutdown()
    if bot_process:
        bot_process.terminate()
        logger.info("Browser bot subprocess terminated.")

app = FastAPI(title="MEXC LTC/USDT Charting API", lifespan=lifespan)

def parse_interval_ms(interval: str) -> int:
    if not interval: return 60000
    unit = interval[-1]
    try:
        value = int(interval[:-1])
    except:
        value = 1
        
    if unit == 'm': return value * 60 * 1000
    elif unit == 'h': return value * 60 * 60 * 1000
    elif unit == 'd': return value * 24 * 60 * 60 * 1000
    return 60 * 1000

def aggregate_candles(candles, interval_ms: int):
    if not candles: return []
    
    aggregated = []
    current_bucket = None
    
    for c in candles:
        bucket_time = (c.timestamp // interval_ms) * interval_ms
        vol = c.volume if c.volume is not None else 0
        
        if current_bucket is None or current_bucket['timestamp'] != bucket_time:
            if current_bucket is not None:
                aggregated.append(current_bucket)
            current_bucket = {
                'timestamp': bucket_time,
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': vol,
            }
        else:
            current_bucket['high'] = max(current_bucket['high'], c.high)
            current_bucket['low'] = min(current_bucket['low'], c.low)
            current_bucket['close'] = c.close
            current_bucket['volume'] = current_bucket['volume'] + vol
            
    if current_bucket is not None:
        aggregated.append(current_bucket)
        
    return aggregated

def get_historical_summary(db: Session):
    l_stats = db.query(
        func.count(TradeHistory.id),
        func.avg(TradeHistory.duration_min),
        func.sum(TradeHistory.averagings)
    ).filter(TradeHistory.type == 1).first()
    
    s_stats = db.query(
        func.count(TradeHistory.id),
        func.avg(TradeHistory.duration_min),
        func.sum(TradeHistory.averagings)
    ).filter(TradeHistory.type == -1).first()
    
    return {
        "l_count": l_stats[0] or 0,
        "l_avg_min": l_stats[1] or 0.0,
        "l_total_avg": l_stats[2] or 0,
        "s_count": s_stats[0] or 0,
        "s_avg_min": s_stats[1] or 0.0,
        "s_total_avg": s_stats[2] or 0
    }

def save_closed_trades(db: Session, closed_trades):
    if not closed_trades: return
    for t in closed_trades:
        exists = db.query(TradeHistory).filter(
            TradeHistory.entry_time == t['entry_time'],
            TradeHistory.exit_time == t['exit_time'],
            TradeHistory.type == t['type']
        ).first()
        if not exists:
            new_trade = TradeHistory(
                type=t['type'],
                entry_time=t['entry_time'],
                exit_time=t['exit_time'],
                averagings=t['averagings'],
                profit=t['profit'],
                duration_min=t['duration_min']
            )
            db.add(new_trade)
    db.commit()

LATEST_1M_STATE = None

def strategy_state_daemon():
    global LATEST_1M_STATE
    while True:
        try:
            db = SessionLocal()
            last_state = db.query(StrategyState).order_by(desc(StrategyState.timestamp_ms)).first()
            
            if last_state:
                last_ts = last_state.timestamp_ms
                initial_state = json.loads(last_state.state_json)
                
                next_candle = db.query(Candle).filter(Candle.timestamp > last_ts).order_by(Candle.timestamp).first()
                if not next_candle:
                    db.close()
                    LATEST_1M_STATE = initial_state
                    time.sleep(1)
                    continue
                
                # We need context for `calculate_step` (which looks back 100 candles).
                # So we fetch 200: 100 for the strategy state + 100 for the step calculation buffer.
                candles_context = db.query(Candle).filter(Candle.timestamp <= next_candle.timestamp).order_by(desc(Candle.timestamp)).limit(200).all()
                candles_context.reverse()
                
                if not candles_context:
                    db.close()
                    time.sleep(1)
                    continue
                    
                process_idx = len(candles_context) - 1
                h = get_historical_summary(db)
                _, _, _, closed_trades, final_state = apply_strategy_ms(
                    candles_context, interval_ms=60000, mnoznik_qty_long=10.0, mnoznik_qty_short=10.0,
                    hist_long_avg_min=h["l_avg_min"], hist_long_count=h["l_count"],
                    hist_short_avg_min=h["s_avg_min"], hist_short_count=h["s_count"],
                    hist_long_total_averagings=h["l_total_avg"], hist_short_total_averagings=h["s_total_avg"],
                    initial_state=initial_state, process_from_index=process_idx, treat_last_as_live=False
                )
                
                save_closed_trades(db, closed_trades)
                
                new_state = StrategyState(
                    timestamp_ms=next_candle.timestamp,
                    state_json=json.dumps(final_state)
                )
                db.add(new_state)
                db.commit()
                LATEST_1M_STATE = final_state
                
            else:
                db_candles = db.query(Candle).order_by(Candle.timestamp).all()
                if not db_candles:
                    db.close()
                    time.sleep(1)
                    continue
                
                h = get_historical_summary(db)
                _, _, _, closed_trades, final_state = apply_strategy_ms(
                    db_candles, interval_ms=60000, mnoznik_qty_long=10.0, mnoznik_qty_short=10.0,
                    hist_long_avg_min=h["l_avg_min"], hist_long_count=h["l_count"],
                    hist_short_avg_min=h["s_avg_min"], hist_short_count=h["s_count"],
                    hist_long_total_averagings=h["l_total_avg"], hist_short_total_averagings=h["s_total_avg"],
                    initial_state=None, process_from_index=0, treat_last_as_live=False
                )
                
                save_closed_trades(db, closed_trades)
                
                new_state = StrategyState(
                    timestamp_ms=db_candles[-1].timestamp,
                    state_json=json.dumps(final_state)
                )
                db.add(new_state)
                db.commit()
                LATEST_1M_STATE = final_state
                
            db.close()
        except Exception as e:
            logger.error(f"Strategy Engine Daemon Error: {e}")
            import traceback
            traceback.print_exc()
            with open('daemon_error.log', 'a') as f:
                f.write(traceback.format_exc() + '\n')
            time.sleep(5)

simulation_anchor_timestamp = None

@app.get("/api/candles")
def get_candles(limit: int = Query(10000), before: int = Query(None), interval: str = Query('1m'), mnoznik_long: float = Query(10.0), mnoznik_short: float = Query(10.0), db: Session = Depends(get_db)):
    global simulation_anchor_timestamp
    
    interval_ms = parse_interval_ms(interval)
    factor = interval_ms // 60000
    db_limit = limit * factor
    
    if simulation_anchor_timestamp is None:
        # Initialize anchor once
        anchor_candle = db.query(Candle).order_by(desc(Candle.timestamp)).limit(db_limit).all()
        if anchor_candle:
            simulation_anchor_timestamp = anchor_candle[-1].timestamp
        else:
            simulation_anchor_timestamp = 0
            
    query = db.query(Candle)
    
    if before:
        query = query.filter(Candle.timestamp < before)
    else:
        # If no 'before' (meaning standard refresh), anchor the query so the simulation starts perfectly fixed
        query = query.filter(Candle.timestamp >= simulation_anchor_timestamp)
        
    candles = query.order_by(Candle.timestamp).all()
    
    # If the user requested history before the anchor, we just use those candles as is.
    
    if factor > 1:
        aggregated = aggregate_candles(candles, interval_ms)
    else:
        aggregated = [{'timestamp': c.timestamp, 'open': c.open, 'high': c.high, 'low': c.low, 'close': c.close, 'volume': c.volume if c.volume is not None else 0} for c in candles]
        
    res = aggregated[-limit:] if limit else aggregated
    
    formatted_candles = [
        {
            "time": int(c['timestamp'] // 1000),
            "open": c['open'],
            "high": c['high'],
            "low": c['low'],
            "close": c['close'],
        }
        for c in res
    ]
    
    # Fetch historical stats from DB
    h = get_historical_summary(db)
    
    # Calculate strategy points on the aggregated/unaggregated candles.
    # We pass the full history (aggregated) we pulled from DB, to give the MA more data to work with.
    strategy_points, markers, panel_text, closed_trades, _ = apply_strategy_ms(
        aggregated, interval_ms, mnoznik_qty_long=mnoznik_long, mnoznik_qty_short=mnoznik_short,
        hist_long_avg_min=h["l_avg_min"], hist_long_count=h["l_count"],
        hist_short_avg_min=h["s_avg_min"], hist_short_count=h["s_count"],
        hist_long_total_averagings=h["l_total_avg"], hist_short_total_averagings=h["s_total_avg"]
    )
    # Save newly detected closed trades
    save_closed_trades(db, closed_trades)
    # Trim strategy_points similarly to how we trim candles
    formatted_strategy = strategy_points[-limit:] if limit else strategy_points
    
    # Filter markers to only show ones relevant to the currently sent candles
    min_time = formatted_candles[0]['time'] if formatted_candles else 0
    filtered_markers = [m for m in markers if m['time'] >= min_time]

    return {
        "candles": formatted_candles,
        "indicator": formatted_strategy,
        "markers": filtered_markers,
        "panel": panel_text
    }

@app.get("/api/current_candle")
def get_current_candle(interval: str = Query('1m'), mnoznik_long: float = Query(10.0), mnoznik_short: float = Query(10.0), db: Session = Depends(get_db)):
    global simulation_anchor_timestamp
    import backend.fetcher as fetcher
    forming = fetcher.current_forming_candle
    if not forming:
        return None
        
    interval_ms = parse_interval_ms(interval)
    final_bucket = None
    
    if interval_ms == 60000:
        final_bucket = forming
    else:
        forming_ms = forming['time'] * 1000
        bucket_time = (forming_ms // interval_ms) * interval_ms
        
        # Get recent closed candles that belong to this bigger bucket
        recent_candles = db.query(Candle).filter(Candle.timestamp >= bucket_time).order_by(Candle.timestamp).all()
        
        if not recent_candles:
            final_bucket = {
                "time": int(bucket_time // 1000),
                "open": forming['open'],
                "high": forming['high'],
                "low": forming['low'],
                "close": forming['close']
            }
        else:
            final_bucket = {
                "time": int(bucket_time // 1000),
                "open": recent_candles[0].open,
                "high": max([c.high for c in recent_candles] + [forming['high']]),
                "low": min([c.low for c in recent_candles] + [forming['low']]),
                "close": forming['close']
            }
            
    # Calculate forming indicator point
    # Use the globally cached stateful engine if interval is 1m
    global LATEST_1M_STATE
    # We only use the stateful cache if it's fully synced up to the current time (within the last few minutes).
    # If the daemon is currently backfilling weeks of data, we fall back to stateless calculation to prevent array offset bugs.
    state_is_synced = False
    if LATEST_1M_STATE is not None:
        # Check timestamp of latest stored state via db
        last_state_row = db.query(StrategyState).order_by(desc(StrategyState.timestamp_ms)).first()
        if last_state_row:
            time_diff_ms = (final_bucket['time'] * 1000) - last_state_row.timestamp_ms
            # If the database state is less than 5 minutes older than the current candle, it's synced.
            if time_diff_ms < (5 * 60 * 1000) and time_diff_ms >= 0:
                state_is_synced = True

    if interval_ms == 60000 and state_is_synced:
        # Limit to 200 to give `calculate_step` enough historical buffer (100 needed)
        context_candles = db.query(Candle).order_by(desc(Candle.timestamp)).limit(200).all()
        context_candles.reverse()
        # Append the real-time forming bucket
        context_candles.append(Candle(
            timestamp=final_bucket['time'] * 1000,
            open=final_bucket['open'],
            high=final_bucket['high'],
            low=final_bucket['low'],
            close=final_bucket['close'],
            volume=0
        ))
        
        process_idx = len(context_candles) - 1
        h = get_historical_summary(db)
        # Use initial state corresponding EXACTLY to context_candles[-2]
        strategy_points, markers, panel_text, closed_trades, _ = apply_strategy_ms(
            context_candles, interval_ms, mnoznik_qty_long=mnoznik_long, mnoznik_qty_short=mnoznik_short,
            hist_long_avg_min=h["l_avg_min"], hist_long_count=h["l_count"],
            hist_short_avg_min=h["s_avg_min"], hist_short_count=h["s_count"],
            hist_long_total_averagings=h["l_total_avg"], hist_short_total_averagings=h["s_total_avg"],
            initial_state=LATEST_1M_STATE, process_from_index=process_idx
        )
        # Do not save closed trades here, as this is just a live tick simulation.
    else:
        # Fallback to stateless calculation for other timeframe rendering or if state is booting
        if simulation_anchor_timestamp is None:
            db_limit = 10000 * max(1, interval_ms // 60000)
            anchor_candle = db.query(Candle).order_by(desc(Candle.timestamp)).limit(db_limit).all()
            simulation_anchor_timestamp = anchor_candle[-1].timestamp if anchor_candle else 0

        history_query = db.query(Candle).filter(Candle.timestamp >= simulation_anchor_timestamp).order_by(Candle.timestamp).all()
        
        if interval_ms > 60000:
            hist_agg = aggregate_candles(history_query, interval_ms)
        else:
            hist_agg = [{'timestamp': c.timestamp, 'open': c.open, 'high': c.high, 'low': c.low, 'close': c.close, 'volume': c.volume if c.volume is not None else 0} for c in history_query]
            
        if hist_agg and hist_agg[-1]['timestamp'] >= final_bucket['time'] * 1000:
            hist_agg.pop()
            
        hist_agg.append({
            'timestamp': final_bucket['time'] * 1000,
            'open': final_bucket['open'],
            'high': final_bucket['high'],
            'low': final_bucket['low'],
            'close': final_bucket['close']
        })
        
        h = get_historical_summary(db)
        strategy_points, markers, panel_text, closed_trades, _ = apply_strategy_ms(
            hist_agg, interval_ms, mnoznik_qty_long=mnoznik_long, mnoznik_qty_short=mnoznik_short,
            hist_long_avg_min=h["l_avg_min"], hist_long_count=h["l_count"],
            hist_long_total_averagings=h["l_total_avg"], hist_short_total_averagings=h["s_total_avg"]
        )
        # Do NOT save closed trades from the API polling! This creates thousands of duplicates!
        # save_closed_trades(db, closed_trades)
    latest_strategy_point = strategy_points[-1] if strategy_points else None
    
    forming_time_sec = int(final_bucket['time'])
    # Never return markers for the forming candle - signals should only appear on closed candles
    recent_markers = []
    
    return {
        "candle": final_bucket,
        "indicator": latest_strategy_point,
        "markers": recent_markers,
        "panel": panel_text,
        "live_position": global_live_position,
        "is_auto_trading": is_auto_trading
    }

# Mount frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
os.makedirs(frontend_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

from pydantic import BaseModel

class PositionState(BaseModel):
    long_amount: float = 0.0
    long_price: float = 0.0
    long_pnl: float = 0.0
    short_amount: float = 0.0
    short_price: float = 0.0
    short_pnl: float = 0.0

class AutoTradeRequest(BaseModel):
    is_auto: bool

global_live_position = {
    "long_amount": 0.0,
    "long_price": 0.0,
    "long_pnl": 0.0,
    "short_amount": 0.0,
    "short_price": 0.0,
    "short_pnl": 0.0
}
is_auto_trading = False

@app.post("/api/live_position")
def update_live_position(state: PositionState):
    global global_live_position
    global_live_position = state.dict()
    return {"status": "ok"}

@app.post("/api/set_auto")
def set_auto_trading(req: AutoTradeRequest):
    global is_auto_trading
    is_auto_trading = req.is_auto
    return {"status": "ok", "is_auto": is_auto_trading}

# --- Manual Trading ---
class ManualTradeRequest(BaseModel):
    action: str
    amount: float

manual_commands_queue = []

@app.post("/api/manual_trade")
def receive_manual_trade(req: ManualTradeRequest):
    manual_commands_queue.append({"action": req.action, "amount": req.amount})
    return {"status": "ok"}

@app.get("/api/get_manual_commands")
def get_manual_commands():
    # Return all queued commands and clear the queue
    cmds = manual_commands_queue.copy()
    manual_commands_queue.clear()
    return {"commands": cmds}

# --- Dev Info ---
@app.get("/api/dev_info")
def get_dev_info(db: Session = Depends(get_db)):
    """Returns counters of closed trades grouped by number of averagings (0..19)."""
    from sqlalchemy import func as sqlfunc
    rows = db.query(
        TradeHistory.averagings,
        sqlfunc.count(TradeHistory.id)
    ).group_by(TradeHistory.averagings).all()

    counts = {int(r[0]): int(r[1]) for r in rows if r[0] is not None}
    counters = []
    for i in range(20):
        counters.append({"averagings": i, "count": counts.get(i, 0)})
    return {"counters": counters}


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))
