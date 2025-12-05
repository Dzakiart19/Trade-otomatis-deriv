#!/usr/bin/env python3
"""
Script untuk mengecek kontrak trading yang tersedia di Deriv.
"""

import os
import time
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

from deriv_ws import DerivWebSocket

contracts_data = None

def on_message_handler(ws, message):
    """Handle incoming messages"""
    global contracts_data
    data = json.loads(message)
    msg_type = data.get("msg_type", "")
    
    if msg_type == "contracts_for":
        contracts_data = data.get("contracts_for", {})
        logger.info("Received contracts data!")
    elif msg_type == "error":
        error = data.get("error", {})
        logger.error(f"Error: {error.get('message', 'Unknown')}")

def check_symbol(deriv, symbol):
    """Check available contracts for a symbol"""
    global contracts_data
    contracts_data = None
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Checking contracts for: {symbol}")
    logger.info(f"{'='*60}")
    
    old_handler = deriv.ws.on_message if deriv.ws else None
    if deriv.ws:
        deriv.ws.on_message = on_message_handler
    
    deriv.get_contracts_for(symbol)
    
    timeout = 10
    start = time.time()
    while contracts_data is None and (time.time() - start) < timeout:
        time.sleep(0.5)
    
    if deriv.ws and old_handler:
        deriv.ws.on_message = old_handler
    
    if contracts_data is None:
        logger.error(f"Timeout getting contracts for {symbol}")
        return
    
    available = contracts_data.get("available", [])
    
    if not available:
        logger.warning(f"No contracts available for {symbol}")
        return
    
    contract_types = {}
    for contract in available:
        ct = contract.get("contract_type", "")
        if ct not in contract_types:
            contract_types[ct] = {
                "min_duration": contract.get("min_contract_duration", ""),
                "max_duration": contract.get("max_contract_duration", ""),
                "barriers": contract.get("barriers", 0),
                "sentiment": contract.get("sentiment", "")
            }
    
    logger.info(f"\nAvailable contract types for {symbol}:")
    for ct, info in contract_types.items():
        logger.info(f"  - {ct}")
        logger.info(f"      Duration: {info['min_duration']} to {info['max_duration']}")
        logger.info(f"      Sentiment: {info['sentiment']}")
    
    return contract_types

def main():
    demo_token = os.getenv("DERIV_TOKEN_DEMO")
    if not demo_token:
        logger.error("DERIV_TOKEN_DEMO not found!")
        return
    
    logger.info("Connecting to Deriv...")
    deriv = DerivWebSocket(
        demo_token=demo_token,
        real_token=os.getenv("DERIV_TOKEN_REAL", "")
    )
    
    deriv.connect()
    
    timeout = 30
    start = time.time()
    while not deriv.is_authorized and (time.time() - start) < timeout:
        time.sleep(0.5)
    
    if not deriv.is_authorized:
        logger.error("Failed to authorize!")
        return
    
    logger.info(f"Connected! Account: {deriv.account_info.account_id if deriv.account_info else 'Unknown'}")
    
    symbols = [
        "frxXAUUSD",
        "R_100",
        "R_50",
        "1HZ100V",
    ]
    
    for symbol in symbols:
        check_symbol(deriv, symbol)
        time.sleep(2)
    
    deriv.disconnect()
    logger.info("\nDone!")

if __name__ == "__main__":
    main()
