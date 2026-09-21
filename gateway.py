import sys
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import MetaTrader5 as mt5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AivanaGateway")

app = FastAPI(title="AIVANA Sovereign MT5 Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def ensure_mt5():
    if not mt5.initialize():
        err = mt5.last_error()
        logger.error(f"MT5 initialize failed: {err}")
        raise HTTPException(status_code=503, detail=f"MT5 initialize failed: {err}")
    return True

TIMEFRAME_DICT = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

@app.on_event("startup")
def startup():
    logger.info("Starting AIVANA MT5 Gateway...")
    try:
        ensure_mt5()
        acc = mt5.account_info()
        if acc:
            logger.info(f"Connected to MT5 Account: {acc.login} | Server: {acc.server} | Balance: {acc.balance} {acc.currency}")
    except Exception as e:
        logger.warning(f"Startup MT5 warning: {e}")

@app.get("/")
@app.get("/health")
def health():
    ensure_mt5()
    acc = mt5.account_info()
    return {
        "status": "online",
        "service": "AIVANA Sovereign Institutional MT5 Gateway",
        "account": acc.login if acc else None,
        "server": acc.server if acc else None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/account")
def get_account():
    ensure_mt5()
    acc = mt5.account_info()
    if not acc:
        raise HTTPException(status_code=503, detail="Cannot read account info")
    return {
        "success": True,
        "login": acc.login,
        "server": acc.server,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "profit": acc.profit,
        "currency": acc.currency,
        "leverage": acc.leverage,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/positions")
def get_positions():
    ensure_mt5()
    positions = mt5.positions_get()
    result = []
    if positions:
        for p in positions:
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "lots": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "comment": p.comment,
                "magic": p.magic,
                "time": p.time
            })
    return {
        "success": True,
        "positions": result,
        "count": len(result),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/klines")
def get_klines(symbol: str = "XAUUSDm", timeframe: str = "M5", limit: int = 2000):
    ensure_mt5()
    clean_sym = symbol.strip()
    if not mt5.symbol_select(clean_sym, True):
        for s in [clean_sym, f"{clean_sym}m", f"{clean_sym}c", clean_sym.replace("m", "").replace("c", "")]:
            if mt5.symbol_select(s, True):
                clean_sym = s
                break
    
    tf_upper = timeframe.upper().strip()
    tf_code = TIMEFRAME_DICT.get(tf_upper, mt5.TIMEFRAME_M5)
    
    rates = mt5.copy_rates_from_pos(clean_sym, tf_code, 0, min(limit, 3000))
    if rates is None or len(rates) == 0:
        raise HTTPException(status_code=404, detail=f"No candle data for {clean_sym} on {timeframe}")
    
    candles = []
    for r in rates:
        candles.append({
            "time": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["tick_volume"])
        })
    
    return {
        "success": True,
        "symbol": clean_sym,
        "timeframe": timeframe,
        "candles": candles,
        "count": len(candles)
    }

class OrderRequest(BaseModel):
    symbol: str = "XAUUSDm"
    type: str = "BUY"
    lots: float = 0.01
    sl: Optional[float] = 0.0
    tp: Optional[float] = 0.0

class CloseRequest(BaseModel):
    ticket: int
    symbol: Optional[str] = None
    lots: Optional[float] = None

@app.post("/api/order")
def place_order(req: OrderRequest):
    ensure_mt5()
    sym = req.symbol.strip()
    if not mt5.symbol_select(sym, True):
        for s in [sym, f"{sym}m", f"{sym}c", sym.replace("m", "").replace("c", "")]:
            if mt5.symbol_select(s, True):
                sym = s
                break
                
    tick = mt5.symbol_info_tick(sym)
    if not tick:
        raise HTTPException(status_code=400, detail=f"Cannot get tick price for {sym}")
        
    is_buy = req.type.upper() == "BUY"
    price = tick.ask if is_buy else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    
    sym_info = mt5.symbol_info(sym)
    filling = mt5.ORDER_FILLING_IOC
    if sym_info:
        if sym_info.filling_mode & 1:
            filling = mt5.ORDER_FILLING_FOK
        elif sym_info.filling_mode & 2:
            filling = mt5.ORDER_FILLING_IOC
        else:
            filling = mt5.ORDER_FILLING_RETURN

    trade_req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": float(req.lots),
        "type": order_type,
        "price": price,
        "sl": float(req.sl) if req.sl else 0.0,
        "tp": float(req.tp) if req.tp else 0.0,
        "deviation": 20,
        "magic": 260101,
        "comment": "AIVANA Sovereign Order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }
    
    result = mt5.order_send(trade_req)
    if not result:
        err = mt5.last_error()
        raise HTTPException(status_code=500, detail=f"Order send failed without result: {err}")
        
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {
            "success": False,
            "retcode": result.retcode,
            "comment": result.comment,
            "error": f"MT5 Retcode {result.retcode}: {result.comment}"
        }
        
    return {
        "success": True,
        "retcode": result.retcode,
        "ticket": result.order,
        "volume": result.volume,
        "price": result.price,
        "symbol": sym,
        "type": req.type.upper()
    }

@app.post("/api/close")
def close_order(req: CloseRequest):
    ensure_mt5()
    pos = mt5.positions_get(ticket=req.ticket)
    if not pos or len(pos) == 0:
        raise HTTPException(status_code=404, detail=f"Position ticket {req.ticket} not found or already closed")
        
    p = pos[0]
    sym = p.symbol
    vol = req.lots if req.lots and req.lots > 0 else p.volume
    is_buy = p.type == 0
    close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    
    tick = mt5.symbol_info_tick(sym)
    if not tick:
        raise HTTPException(status_code=400, detail=f"Cannot get tick price for {sym}")
        
    price = tick.bid if is_buy else tick.ask
    
    sym_info = mt5.symbol_info(sym)
    filling = mt5.ORDER_FILLING_IOC
    if sym_info:
        if sym_info.filling_mode & 1:
            filling = mt5.ORDER_FILLING_FOK
        elif sym_info.filling_mode & 2:
            filling = mt5.ORDER_FILLING_IOC
        else:
            filling = mt5.ORDER_FILLING_RETURN

    trade_req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": req.ticket,
        "symbol": sym,
        "volume": float(vol),
        "type": close_type,
        "price": price,
        "deviation": 20,
        "magic": 260101,
        "comment": "AIVANA Sovereign Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }
    
    result = mt5.order_send(trade_req)
    if not result:
        err = mt5.last_error()
        raise HTTPException(status_code=500, detail=f"Close order failed: {err}")
        
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {
            "success": False,
            "retcode": result.retcode,
            "comment": result.comment,
            "error": f"MT5 Retcode {result.retcode}: {result.comment}"
        }
        
    return {
        "success": True,
        "retcode": result.retcode,
        "ticket": result.order,
        "volume": result.volume,
        "price": result.price
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8050)
