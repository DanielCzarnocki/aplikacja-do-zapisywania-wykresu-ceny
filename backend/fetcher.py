import ccxt
import logging
import time
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from backend.database import SessionLocal
from backend.models import Candle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MEXC exchange
exchange = ccxt.mexc()

# Global dictionary to hold the currently forming candle
current_forming_candle = None

def fetch_and_store_candles():
    global current_forming_candle
    symbol = 'LTC/USDT'
    timeframe = '1m'
    limit = 100 # Fetch last 100 candles

    try:
        # Fetch OHLCV: [timestamp, open, high, low, close, volume]
        ohlcvs = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not ohlcvs:
            return
            
        db: Session = SessionLocal()
        new_candles_count = 0
        
        # The last candle in the array is the currently forming one
        forming_candle_data = ohlcvs[-1]
        timestamp = forming_candle_data[0]
        current_forming_candle = {
            "time": int(timestamp // 1000),
            "open": forming_candle_data[1],
            "high": forming_candle_data[2],
            "low": forming_candle_data[3],
            "close": forming_candle_data[4],
            "volume": forming_candle_data[5]
        }
        
        # All candles before the last one are considered "closed"
        closed_candles = ohlcvs[:-1]
        
        for ohlcv in closed_candles:
            timestamp, open_price, high, low, close, volume = ohlcv
            
            # Check if closed candle already exists in db
            existing_candle = db.query(Candle).filter(Candle.timestamp == timestamp).first()
            if not existing_candle:
                candle = Candle(
                    timestamp=timestamp,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume
                )
                db.add(candle)
                new_candles_count += 1
                
        db.commit()
        db.close()
        
        if new_candles_count > 0:
            logger.info(f"Successfully stored {new_candles_count} new closed candles.")
        
    except Exception as e:
        logger.error(f"Error fetching/storing candles: {e}")

def backfill_missing_candles():
    """
    Background process to fill gaps (auto-healing) and verify/download historical data.
    """
    symbol = 'LTC/USDT'
    timeframe = '1m'
    db: Session = SessionLocal()
    
    try:
        logger.info("Starting full historical data sync and verification...")
        
        current_time_ms = int(time.time() * 1000)
        end_ms = current_time_ms
        empty_count = 0
        
        while True:
            # We fetch forward from this start_ms
            start_ms = end_ms - (1000 * 60000)
            ohlcvs = exchange.fetch_ohlcv(symbol, timeframe, since=start_ms, limit=1000)
            
            if not ohlcvs:
                empty_count += 1
                if empty_count > 14: # ~10 days of completely empty data
                    logger.info("Sync: Reached the beginning of available history or a very large gap.")
                    break
                end_ms = start_ms
            else:
                empty_count = 0
                actual_start_ms = ohlcvs[0][0]
                actual_end_ms = ohlcvs[-1][0]
                
                # Fetch existing candles in this time range into a map
                existing_candles = db.query(Candle).filter(
                    Candle.timestamp >= actual_start_ms, 
                    Candle.timestamp <= actual_end_ms
                ).all()
                existing_map = {c.timestamp: c for c in existing_candles}
                
                added = 0
                updated = 0
                
                for ohlcv in ohlcvs:
                    ts, o, h, l, c, v = ohlcv
                    if ts >= current_time_ms - 60000: # Don't process currently forming minute
                        continue
                        
                    if ts in existing_map:
                        existing = existing_map[ts]
                        # If existing, compare and update
                        if existing.open != o or existing.high != h or existing.low != l or existing.close != c or existing.volume != v:
                            existing.open = o
                            existing.high = h
                            existing.low = l
                            existing.close = c
                            existing.volume = v
                            updated += 1
                    else:
                        # Missing entirely, insert
                        db.add(Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v))
                        added += 1
                
                db.commit()
                if added > 0 or updated > 0:
                    logger.info(f"Sync ({actual_start_ms}-{actual_end_ms}): Added {added}, Updated {updated} older candles.")
                
                if actual_start_ms < end_ms:
                    end_ms = actual_start_ms
                else:
                    end_ms = start_ms
                    
            time.sleep(0.5) # Compliance with rate limits
            
        logger.info("Historical verification and backfill process entirely completed.")

    except Exception as e:
        logger.error(f"Error during full sync backfill: {e}")
    finally:
        db.close()
