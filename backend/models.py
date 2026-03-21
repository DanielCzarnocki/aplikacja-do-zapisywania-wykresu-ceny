from sqlalchemy import Column, Integer, Float, BigInteger, String
from backend.database import Base

class Candle(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(BigInteger, unique=True, index=True) # timestamp in milliseconds
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)

class TradeHistory(Base):
    __tablename__ = "trade_history"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(Integer)  # 1 for LONG, -1 for SHORT
    entry_time = Column(BigInteger)
    exit_time = Column(BigInteger)
    averagings = Column(Integer)
    profit = Column(Float)
    duration_min = Column(Float)

class StrategyState(Base):
    __tablename__ = "strategy_state"

    id = Column(Integer, primary_key=True, index=True)
    timestamp_ms = Column(BigInteger, unique=True, index=True) # the timestamp of the last processed candle
    state_json = Column(String) # JSON payload of L_system_aktywny, etc.
