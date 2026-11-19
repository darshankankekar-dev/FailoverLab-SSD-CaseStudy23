"""
FAILOVERLAB - LIVE DEMONSTRATION TRAFFIC GENERATOR
Companion CLI tool for live demonstrations.

Usage:
  python scripts/demo_traffic.py --mode shop      # Continuous shopping traffic (browse & buy)
  python scripts/demo_traffic.py --mode burst     # Rapid burst to trigger 429 rate limiting
  python scripts/demo_traffic.py --mode failover  # Trigger live failover to Region B
  python scripts/demo_traffic.py --mode fence     # Verify fencing & split-brain rejection on old primary
"""

import argparse
import json
import random
import sys
import time
import urllib.request
import urllib.error

GATEWAY_URL = "http://localhost:8080"
CONTROLLER_URL = "http://localhost:8000"
REGION_A_URL = "http://localhost:8001"
ADMIN_SECRET = "supersecret-admin-token"


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def run_continuous_shopping(duration_seconds: int = 60, delay: float = 1.0):
    log("Starting continuous shopping traffic generator...")
    log(f"Target: {GATEWAY_URL} | Duration: {duration_seconds}s | Interval: {delay}s\n")
    start = time.time()
    order_num = 1

    while time.time() - start < duration_seconds:
        try:
            # 1. Browse products (Eventual consistency read)
            req = urllib.request.Request(f"{GATEWAY_URL}/api/ecommerce/products")
            with urllib.request.urlopen(req, timeout=3.0) as res:
                products = json.loads(res.read().decode())
                served_region = res.headers.get("X-Served-Region", "unknown")
                log(f" [Browse] Catalog loaded ({len(products)} items) via {served_region} [HTTP {res.status}]")

            # 2. Pick a random item and place order (Strong consistency write)
            prod = random.choice(products)
            order_payload = {
                "product_id": prod["id"],
                "quantity": 1,
                "customer_name": f"Live Shopper #{order_num}",
                "customer_email": f"shopper_{order_num}@demo.failoverlab.local",
            }
            req = urllib.request.Request(
                f"{GATEWAY_URL}/api/ecommerce/orders",
                data=json.dumps(order_payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as res:
                order = json.loads(res.read().decode())
                served_region = res.headers.get("X-Served-Region", "unknown")
                log(f"  [Order Placed] Order {order['order_id']} for '${order['total_amount']}' -> {served_region} [HTTP {res.status}]")
                order_num += 1

        except urllib.error.HTTPError as e:
            log(f" [HTTP Error] {e.code}: {e.reason}")
        except Exception as e:
            log(f" [Network Error] {e}")

        time.sleep(delay)

    log("\nContinuous shopping run complete.")


def run_burst(count: int = 35):
    log(f"Triggering high-frequency burst ({count} requests in parallel/rapid succession)...")
    success = 0
    rate_limited = 0

    for i in range(count):
        try:
            req = urllib.request.Request(f"{GATEWAY_URL}/api/ecommerce/products")
            with urllib.request.urlopen(req, timeout=2.0) as res:
                success += 1
        except urllib.error.HTTPError as e:
            if e.code == 429:
                rate_limited += 1
            else:
                log(f"Request {i+1} returned {e.code}")
        except Exception:
            pass
        time.sleep(0.02)  # 20ms spacing

    log(f"\nBurst Results:")
    log(f"  -> Successful (200 OK): {success}")
    log(f"  -> Rate-Limited (429 Too Many Requests): {rate_limited}")
    log("Check Controller Dashboard (http://localhost:5173/controller) to see the 429 spike!\n")


def trigger_failover(target_region: str = "region-b"):
    log(f"Initiating controlled failover to {target_region.upper()} via Controller...")
    url = f"{CONTROLLER_URL}/api/v1/failover/trigger"
    payload = {
        "target_region": target_region,
        "reason": "Live demonstration of zero-downtime regional promotion",
        "operator": "Presenter",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Admin-Secret": ADMIN_SECRET,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as res:
            data = json.loads(res.read().decode())
            log(f"Failover successful! New Active Primary: {data.get('active_region', target_region)}")
            log(f"New Fencing Epoch: {data.get('fencing_epoch', 'incremented')}")
            log("Now check http://localhost:5173/shop to observe writes going to Singapore (region-b)!")
    except urllib.error.HTTPError as e:
        log(f"Failover failed [HTTP {e.code}]: {e.read().decode()}")
    except Exception as e:
        log(f"Error triggering failover: {e}")


def test_fencing():
    log("Testing Split-Brain Prevention: Sending stale-epoch write directly to demoted Region A...")
    url = f"{REGION_A_URL}/api/ecommerce/orders"
    stale_payload = {
        "product_id": "prod-laptop-01",
        "quantity": 1,
        "customer_name": "Zombie Writer Attack",
        "fencing_epoch": 1,  # Stale epoch
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(stale_payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as res:
            log(f"⚠️ Unexpected: Write was accepted with HTTP {res.status}")
    except urllib.error.HTTPError as e:
        log(f" SUCCESS: Stale write was blocked by Region A with HTTP {e.code} ({e.reason})!")
        log(f"  Response body: {e.read().decode()}")
        log("Split-brain safely prevented via Fencing Tokens!")
    except Exception as e:
        log(f"Connection error: {e}")


def main():
    parser = argparse.ArgumentParser(description="FailoverLab Live Demo Tool")
    parser.add_argument(
        "--mode",
        choices=["shop", "burst", "failover", "fence", "all"],
        default="shop",
        help="Demo mode to execute",
    )
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds for shop mode")
    parser.add_argument("--burst-count", type=int, default=35, help="Number of requests for burst mode")
    parser.add_argument("--target", default="region-b", help="Target region for failover mode")

    args = parser.parse_args()

    if args.mode == "shop":
        run_continuous_shopping(duration_seconds=args.duration)
    elif args.mode == "burst":
        run_burst(count=args.burst_count)
    elif args.mode == "failover":
        trigger_failover(target_region=args.target)
    elif args.mode == "fence":
        test_fencing()
    elif args.mode == "all":
        log("Running complete demo traffic sequence...")
        run_continuous_shopping(duration_seconds=10)
        time.sleep(1)
        run_burst(count=30)
        time.sleep(1)
        trigger_failover("region-b")
        time.sleep(1)
        test_fencing()
        time.sleep(1)
        run_continuous_shopping(duration_seconds=10)


if __name__ == "__main__":
    main()
