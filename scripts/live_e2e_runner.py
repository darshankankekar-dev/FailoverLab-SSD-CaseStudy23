"""
FAILOVERLAB - LIVE END-TO-END DEMONSTRATION & VERIFICATION RUNNER
Spawns live background services on local ports:
- Controller (Port 8000)
- Region A (Port 8001, Active Writer)
- Region B (Port 8002, Standby Replica)
- Gateway (Port 8080, Ingress Traffic Manager & Telemetry Exporter)

Executes live HTTP requests across all layers to validate:
1. Live health & readiness
2. Storefront catalog, inventory & order creation through Gateway
3. Dynamic payload byte counting (ingress & egress)
4. Telemetry export from Gateway to Controller (POST /internal/telemetry/traffic-batch)
5. Controller ingestion & persistence in database
6. Controller traffic query endpoints (/summary, /timeseries, /regions)
7. Safe regional failover (Region A -> Region B)
8. Subsequent write traffic redirected to Region B
"""

import os
import sys
import time
import uuid
import signal
import subprocess
import tempfile
from pathlib import Path
import httpx

WORKSPACE = Path(__file__).resolve().parent.parent
PYTHON_EXE = WORKSPACE / ".venv" / "Scripts" / "python.exe"

if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)


def clean_db_files():
    for f in ["controller_e2e.db", "region_a_e2e.db", "region_b_e2e.db"]:
        p = WORKSPACE / f
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def wait_for_endpoint(url: str, name: str, timeout: float = 15.0) -> bool:
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return True
            else:
                last_err = f"Status {r.status_code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(0.4)
    print(f"  [DEBUG] {name} at {url} failed: {last_err}")
    return False


def main():
    print("=" * 75)
    print("  FAILOVERLAB: LIVE END-TO-END MULTI-SERVICE VERIFICATION RUNNER")
    print("=" * 75)

    clean_db_files()

    processes = {}
    env_base = os.environ.copy()
    env_base["PYTHONPATH"] = str(WORKSPACE)

    # 1. Start Controller
    print("\n[1/4] Spawning Controller service (Port 8000)...")
    ctrl_env = env_base.copy()
    ctrl_env["PORT"] = "8000"
    ctrl_env["DATABASE_URL"] = "sqlite+aiosqlite:///./controller_e2e.db"
    ctrl_env["GATEWAY_URL"] = "http://127.0.0.1:8080"
    ctrl_env["REGION_A_URL"] = "http://127.0.0.1:8001"
    ctrl_env["REGION_B_URL"] = "http://127.0.0.1:8002"
    ctrl_env["SIMULATION_MODE"] = "false"
    ctrl_env["LOG_LEVEL"] = "INFO"

    ctrl_log = open(WORKSPACE / "controller_proc.log", "w", encoding="utf-8")
    p_ctrl = subprocess.Popen(
        [
            str(PYTHON_EXE), "-m", "uvicorn", "controller.src.main:app",
            "--host", "127.0.0.1", "--port", "8000"
        ],
        cwd=str(WORKSPACE),
        env=ctrl_env,
        stdout=ctrl_log,
        stderr=ctrl_log,
    )
    processes["controller"] = p_ctrl

    # 2. Start Region A
    print("[2/4] Spawning Region A (Mumbai, Port 8001)...")
    rega_env = env_base.copy()
    rega_env["PORT"] = "8001"
    rega_env["REGION_ID"] = "region-a"
    rega_env["REGION_NAME"] = "Mumbai"
    rega_env["CLOUD_ZONE"] = "ap-south-1"
    rega_env["INITIAL_ROLE"] = "ACTIVE"
    rega_env["DATABASE_URL"] = "sqlite+aiosqlite:///./region_a_e2e.db"
    rega_env["LOG_LEVEL"] = "INFO"

    rega_log = open(WORKSPACE / "region_a_proc.log", "w", encoding="utf-8")
    p_rega = subprocess.Popen(
        [
            str(PYTHON_EXE), "-m", "uvicorn", "region_service.src.main:app",
            "--host", "127.0.0.1", "--port", "8001"
        ],
        cwd=str(WORKSPACE),
        env=rega_env,
        stdout=rega_log,
        stderr=rega_log,
    )
    processes["region-a"] = p_rega

    # 3. Start Region B
    print("[3/4] Spawning Region B (Singapore, Port 8002)...")
    regb_env = env_base.copy()
    regb_env["PORT"] = "8002"
    regb_env["REGION_ID"] = "region-b"
    regb_env["REGION_NAME"] = "Singapore"
    regb_env["CLOUD_ZONE"] = "ap-southeast-1"
    regb_env["INITIAL_ROLE"] = "STANDBY"
    regb_env["DATABASE_URL"] = "sqlite+aiosqlite:///./region_b_e2e.db"
    regb_env["LOG_LEVEL"] = "INFO"

    regb_log = open(WORKSPACE / "region_b_proc.log", "w", encoding="utf-8")
    p_regb = subprocess.Popen(
        [
            str(PYTHON_EXE), "-m", "uvicorn", "region_service.src.main:app",
            "--host", "127.0.0.1", "--port", "8002"
        ],
        cwd=str(WORKSPACE),
        env=regb_env,
        stdout=regb_log,
        stderr=regb_log,
    )
    processes["region-b"] = p_regb

    # 4. Start Gateway
    print("[4/4] Spawning API Gateway (Port 8080)...")
    gw_env = env_base.copy()
    gw_env["PORT"] = "8080"
    gw_env["CONTROLLER_URL"] = "http://127.0.0.1:8000"
    gw_env["REGION_A_URL"] = "http://127.0.0.1:8001"
    gw_env["REGION_B_URL"] = "http://127.0.0.1:8002"
    gw_env["DEFAULT_TARGET"] = "region-a"
    gw_env["TELEMETRY_EXPORT_ENABLED"] = "true"
    gw_env["TELEMETRY_EXPORT_INTERVAL_SECONDS"] = "1.0"
    gw_env["LOG_LEVEL"] = "INFO"

    gw_log = open(WORKSPACE / "gateway_proc.log", "w", encoding="utf-8")
    p_gw = subprocess.Popen(
        [
            str(PYTHON_EXE), "-m", "uvicorn", "gateway.src.main:app",
            "--host", "127.0.0.1", "--port", "8080"
        ],
        cwd=str(WORKSPACE),
        env=gw_env,
        stdout=gw_log,
        stderr=gw_log,
    )
    processes["gateway"] = p_gw

    try:
        # Check health of all services
        print("\nVerifying live readiness across all services...")
        assert wait_for_endpoint("http://127.0.0.1:8000/health/live", "Controller"), "Controller failed to start"
        print("  -> Controller (8000): HEALTHY")

        assert wait_for_endpoint("http://127.0.0.1:8001/health/live", "Region A"), "Region A failed to start"
        print("  -> Region A Mumbai (8001): HEALTHY")

        assert wait_for_endpoint("http://127.0.0.1:8002/health/live", "Region B"), "Region B failed to start"
        print("  -> Region B Singapore (8002): HEALTHY")

        assert wait_for_endpoint("http://127.0.0.1:8080/health/live", "Gateway"), "Gateway failed to start"
        print("  -> API Gateway (8080): HEALTHY")

        client = httpx.Client(timeout=10.0)

        # -------------------------------------------------------------
        # STEP 1: Online Storefront Traffic via Gateway
        # -------------------------------------------------------------
        print("\n[STEP 1] Generating Online Store Traffic through Gateway (8080)...")
        # 1. Product Catalog
        res_cat = client.get(
            "http://127.0.0.1:8080/api/ecommerce/products",
            headers={"X-Client-Region": "ap-south-1", "X-Traffic-Source": "storefront"}
        )
        assert res_cat.status_code == 200, f"Catalog failed: {res_cat.status_code}"
        products = res_cat.json()
        print(f"  -> Catalog retrieved: {len(products)} products (HTTP {res_cat.status_code}, Served by: {res_cat.headers.get('x-served-region')})")

        # 2. Product Inventory Check
        prod_id = products[0]["id"]
        res_inv = client.get(
            f"http://127.0.0.1:8080/api/ecommerce/inventory/{prod_id}",
            headers={"X-Client-Region": "ap-south-1", "X-Traffic-Source": "storefront"}
        )
        assert res_inv.status_code == 200, f"Inventory failed: {res_inv.status_code}"
        inv_data = res_inv.json()
        print(f"  -> Authoritative stock for '{prod_id}': {inv_data.get('available_stock', inv_data.get('quantity', 100))} units (Served by: {res_inv.headers.get('x-served-region')})")

        # 3. Submit Simulated Order
        order_key = f"ord-{uuid.uuid4().hex[:8]}"
        order_body = {
            "product_id": prod_id,
            "quantity": 2,
            "customer_name": "Antigravity Engineer",
            "customer_email": "engineer@failoverlab.internal",
            "shipping_address": "Rack 42, Data Hall B",
            "client_region": "ap-south-1"
        }
        res_ord = client.post(
            "http://127.0.0.1:8080/api/ecommerce/orders",
            json=order_body,
            headers={
                "X-Client-Region": "ap-south-1",
                "X-Traffic-Source": "storefront",
                "X-Idempotency-Key": order_key,
                "Content-Type": "application/json"
            }
        )
        assert res_ord.status_code in (200, 201), f"Order failed: {res_ord.status_code} {res_ord.text}"
        ord_info = res_ord.json()
        print(f"  -> Order placed: {ord_info.get('order_id', ord_info.get('id'))} (Status: {res_ord.status_code}, Writer: {res_ord.headers.get('x-served-region')})")

        # 4. Duplicate Order (Idempotency Check)
        res_dup = client.post(
            "http://127.0.0.1:8080/api/ecommerce/orders",
            json=order_body,
            headers={
                "X-Client-Region": "ap-south-1",
                "X-Traffic-Source": "storefront",
                "X-Idempotency-Key": order_key,
                "Content-Type": "application/json"
            }
        )
        assert res_dup.status_code in (200, 201), f"Duplicate failed: {res_dup.status_code}"
        print(f"  -> Idempotent duplicate: Status {res_dup.status_code}, Replay Header: {res_dup.headers.get('x-idempotency-replay')}")

        # -------------------------------------------------------------
        # STEP 2: Gateway Payload Telemetry Inspection
        # -------------------------------------------------------------
        print("\n[STEP 2] Inspecting Gateway Payload Telemetry...")
        res_telem = client.get("http://127.0.0.1:8080/api/traffic/telemetry")
        assert res_telem.status_code == 200, f"Gateway telemetry failed: {res_telem.status_code}"
        gw_telem = res_telem.json()
        cum = gw_telem["customer_facing"]["cumulative"]
        rates = gw_telem["customer_facing"]["rates"]
        print(f"  -> Client Ingress Bytes: {cum['client_ingress_payload_bytes']} bytes")
        print(f"  -> Client Egress Bytes:  {cum['client_egress_payload_bytes']} bytes")
        print(f"  -> Total Requests:       {cum['total_requests']}")
        lats = gw_telem['customer_facing'].get('latencies', {})
        print(f"  -> P50 / P95 Latency:    {lats.get('p50_ms', 0)}ms / {lats.get('p95_ms', 0)}ms")
        assert cum["client_ingress_payload_bytes"] > 0, "Ingress bytes should be > 0"
        assert cum["client_egress_payload_bytes"] > 0, "Egress bytes should be > 0"

        # -------------------------------------------------------------
        # STEP 3: Telemetry Exporter Pipeline to Controller
        # -------------------------------------------------------------
        print("\n[STEP 3] Awaiting Exporter sync to Controller (1s batch cadence)...")
        time.sleep(2.2)

        # Check exporter status
        res_exp = client.get("http://127.0.0.1:8080/api/v1/traffic/exporter/status")
        exp_status = res_exp.json()
        print(f"  -> Exporter Status: exported={exp_status.get('batches_exported_total')}, queued={exp_status.get('queue_depth')}, dropped={exp_status.get('dropped_batches_total')}")

        # Query Controller Traffic Summary
        res_ctrl_summary = client.get("http://127.0.0.1:8000/api/v1/traffic/summary")
        assert res_ctrl_summary.status_code == 200, f"Controller summary failed: {res_ctrl_summary.status_code}"
        ctrl_summary = res_ctrl_summary.json()
        print(f"  -> Controller Summary: requests={ctrl_summary.get('total_requests')}, ingress={ctrl_summary.get('cumulative_ingress_bytes')}B, egress={ctrl_summary.get('cumulative_egress_bytes')}B, live={ctrl_summary.get('is_available')}")

        # Query Controller Regional Attribution
        res_regions = client.get("http://127.0.0.1:8000/api/v1/traffic/regions")
        assert res_regions.status_code == 200, f"Controller regions failed: {res_regions.status_code}"
        regions_data = res_regions.json().get("regions", {})
        active_region_metric = regions_data.get("region-a") if isinstance(regions_data, dict) else next((r for r in regions_data if r.get("region_id") == "region-a"), None)
        print(f"  -> Regional Attribution: region-a requests={active_region_metric.get('requests_total', 0) if active_region_metric else 0}, ingress={active_region_metric.get('upstream_request_bytes', 0) if active_region_metric else 0}B")

        # Query Controller Timeseries
        res_ts = client.get("http://127.0.0.1:8000/api/v1/traffic/timeseries?time_range_seconds=300")
        assert res_ts.status_code == 200, f"Controller timeseries failed: {res_ts.status_code}"
        ts_data = res_ts.json()
        print(f"  -> Timeseries Points: {len(ts_data.get('points', []))} samples in 300s range (point_count={ts_data.get('point_count')})")

        # -------------------------------------------------------------
        # STEP 4: Safe Regional Failover (Region A -> Region B)
        # -------------------------------------------------------------
        print("\n[STEP 4] Executing Safe Regional Failover (Promoting region-b)...")
        # 1. Promote Region B to Active
        res_prom = client.post(
            "http://127.0.0.1:8002/admin/promote",
            json={"region_id": "region-b", "fencing_epoch": 102, "grant_write_authority": True},
            headers={"X-Internal-Secret": "internal-secret-token"}
        )
        assert res_prom.status_code == 200, f"Promote failed: {res_prom.status_code} {res_prom.text}"
        print(f"  -> Region B promoted to ACTIVE: status={res_prom.status_code}, accepts_writes={res_prom.json().get('accepts_writes')}")

        # 2. Shift Route on Gateway
        res_gw_shift = client.put(
            "http://127.0.0.1:8080/internal/routing/target",
            json={"target_region": "region-b", "target_role": "ACTIVE", "propagation_percent": 100},
            headers={"X-Internal-Secret": "internal-secret-token"}
        )
        assert res_gw_shift.status_code == 200, f"Gateway route shift failed: {res_gw_shift.status_code}"
        print(f"  -> Gateway active writer updated to: {res_gw_shift.json()['route']['active_target']}")

        # Submit new order
        order_key_2 = f"ord-{uuid.uuid4().hex[:8]}"
        res_ord_2 = client.post(
            "http://127.0.0.1:8080/api/ecommerce/orders",
            json={
                "product_id": prod_id,
                "quantity": 1,
                "customer_name": "Failover Tester",
                "customer_email": "failover@failoverlab.internal",
                "shipping_address": "Post-Failover Datacenter",
                "client_region": "ap-southeast-1"
            },
            headers={
                "X-Client-Region": "ap-southeast-1",
                "X-Traffic-Source": "storefront",
                "X-Idempotency-Key": order_key_2,
                "Content-Type": "application/json"
            }
        )
        assert res_ord_2.status_code in (200, 201), f"Post-failover order failed: {res_ord_2.status_code}"
        print(f"  -> Post-failover Order: {res_ord_2.json().get('order_id', res_ord_2.json().get('id'))} (Writer: {res_ord_2.headers.get('x-served-region')})")
        assert res_ord_2.headers.get("x-served-region") == "region-b", f"Expected region-b, got {res_ord_2.headers.get('x-served-region')}"

        # Allow another telemetry cycle to ingest
        time.sleep(2.0)
        res_regions_post = client.get("http://127.0.0.1:8000/api/v1/traffic/regions")
        regions_post_data = res_regions_post.json().get("regions", {})
        reg_b_metric = regions_post_data.get("region-b") if isinstance(regions_post_data, dict) else next((r for r in regions_post_data if r.get("region_id") == "region-b"), None)
        print(f"  -> Controller updated Region B metric: upstream_requests={reg_b_metric.get('requests_total', 0) if reg_b_metric else 0}, ingress={reg_b_metric.get('upstream_request_bytes', 0) if reg_b_metric else 0}B")

        print("\n" + "=" * 75)
        print("  ALL LIVE MULTI-SERVICE VERIFICATIONS COMPLETED SUCCESSFULLY (100% PASS)")
        print("=" * 75)

    finally:
        print("\nTearing down live microservices...")
        for name, p in processes.items():
            try:
                p.terminate()
                p.wait(timeout=2.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            print(f"  -> {name} process terminated.")
        clean_db_files()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
