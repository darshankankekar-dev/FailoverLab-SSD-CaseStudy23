"""
FAILOVERLAB - FULL STACK SERVICE ORCHESTRATOR
Starts all backend microservices and the Vite frontend dev server for interactive usage.

Ports:
- 5173: Frontend Web UI (Online Store at /shop, Controller at /controller, Ops Console at /)
- 8000: Controller Service & Telemetry Storage
- 8001: Region A (Mumbai, Active Writer)
- 8002: Region B (Singapore, Standby Replica)
- 8080: Ingress API Gateway with Telemetry Exporter
"""

import os
import sys
import time
import shutil
import atexit
import signal
import subprocess
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
PYTHON_EXE = WORKSPACE / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

processes = []


def cleanup():
    if not processes:
        return
    print("\nShutting down all FailoverLab services...")
    for name, p in list(processes):
        try:
            p.terminate()
            p.wait(timeout=2.0)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        print(f"  -> {name} stopped.")
    processes.clear()
    print("All services stopped.")


atexit.register(cleanup)


def main():
    print("=" * 75)
    print("  STARTING FAILOVERLAB FULL SYSTEM STACK")
    print("=" * 75)

    env_base = os.environ.copy()
    env_base["PYTHONPATH"] = str(WORKSPACE)

    # 1. Controller
    print("[1/9] Launching Controller on http://localhost:8000 ...")
    ctrl_env = env_base.copy()
    ctrl_env["PORT"] = "8000"
    ctrl_env["DATABASE_URL"] = "sqlite+aiosqlite:///./controller.db"
    ctrl_env["GATEWAY_URL"] = "http://127.0.0.1:8080"
    ctrl_env["REGION_A_URL"] = "http://127.0.0.1:8001"
    ctrl_env["REGION_B_URL"] = "http://127.0.0.1:8002"
    ctrl_env["REGION_C_URL"] = "http://127.0.0.1:8004"
    ctrl_env["REGION_D_URL"] = "http://127.0.0.1:8005"
    ctrl_env["REGION_E_URL"] = "http://127.0.0.1:8006"
    ctrl_env["REPLICATION_WORKER_URL"] = "http://127.0.0.1:8003"
    ctrl_env["SIMULATION_MODE"] = "false"
    p_ctrl = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "controller.src.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(WORKSPACE),
        env=ctrl_env,
    )
    processes.append(("Controller", p_ctrl))

    # 2. Region A (Mumbai)
    print("[2/9] Launching Region A (Mumbai, Active Writer) on http://localhost:8001 ...")
    rega_env = env_base.copy()
    rega_env["PORT"] = "8001"
    rega_env["REGION_ID"] = "region-a"
    rega_env["REGION_NAME"] = "Mumbai"
    rega_env["CLOUD_ZONE"] = "ap-south-1"
    rega_env["INITIAL_ROLE"] = "ACTIVE"
    rega_env["DATABASE_URL"] = "sqlite+aiosqlite:///./region_a.db"
    p_rega = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "region_service.src.main:app", "--host", "0.0.0.0", "--port", "8001"],
        cwd=str(WORKSPACE),
        env=rega_env,
    )
    processes.append(("Region A (Mumbai)", p_rega))

    # 3. Region B (Singapore)
    print("[3/9] Launching Region B (Singapore, Standby) on http://localhost:8002 ...")
    regb_env = env_base.copy()
    regb_env["PORT"] = "8002"
    regb_env["REGION_ID"] = "region-b"
    regb_env["REGION_NAME"] = "Singapore"
    regb_env["CLOUD_ZONE"] = "ap-southeast-1"
    regb_env["INITIAL_ROLE"] = "STANDBY"
    regb_env["DATABASE_URL"] = "sqlite+aiosqlite:///./region_b.db"
    p_regb = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "region_service.src.main:app", "--host", "0.0.0.0", "--port", "8002"],
        cwd=str(WORKSPACE),
        env=regb_env,
    )
    processes.append(("Region B (Singapore)", p_regb))

    # 4. Region C (Frankfurt)
    print("[4/9] Launching Region C (Frankfurt, Standby) on http://localhost:8004 ...")
    regc_env = env_base.copy()
    regc_env["PORT"] = "8004"
    regc_env["REGION_ID"] = "region-c"
    regc_env["REGION_NAME"] = "Frankfurt"
    regc_env["CLOUD_ZONE"] = "eu-central-1"
    regc_env["INITIAL_ROLE"] = "STANDBY"
    regc_env["DATABASE_URL"] = "sqlite+aiosqlite:///./region_c.db"
    p_regc = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "region_service.src.main:app", "--host", "0.0.0.0", "--port", "8004"],
        cwd=str(WORKSPACE),
        env=regc_env,
    )
    processes.append(("Region C (Frankfurt)", p_regc))

    # 5. Region D (Virginia)
    print("[5/9] Launching Region D (Virginia, Standby) on http://localhost:8005 ...")
    regd_env = env_base.copy()
    regd_env["PORT"] = "8005"
    regd_env["REGION_ID"] = "region-d"
    regd_env["REGION_NAME"] = "Virginia"
    regd_env["CLOUD_ZONE"] = "us-east-1"
    regd_env["INITIAL_ROLE"] = "STANDBY"
    regd_env["DATABASE_URL"] = "sqlite+aiosqlite:///./region_d.db"
    p_regd = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "region_service.src.main:app", "--host", "0.0.0.0", "--port", "8005"],
        cwd=str(WORKSPACE),
        env=regd_env,
    )
    processes.append(("Region D (Virginia)", p_regd))

    # 6. Region E (São Paulo)
    print("[6/9] Launching Region E (São Paulo, Standby) on http://localhost:8006 ...")
    rege_env = env_base.copy()
    rege_env["PORT"] = "8006"
    rege_env["REGION_ID"] = "region-e"
    rege_env["REGION_NAME"] = "São Paulo"
    rege_env["CLOUD_ZONE"] = "sa-east-1"
    rege_env["INITIAL_ROLE"] = "STANDBY"
    rege_env["DATABASE_URL"] = "sqlite+aiosqlite:///./region_e.db"
    p_rege = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "region_service.src.main:app", "--host", "0.0.0.0", "--port", "8006"],
        cwd=str(WORKSPACE),
        env=rege_env,
    )
    processes.append(("Region E (São Paulo)", p_rege))

    # 7. Asynchronous Replication Worker
    print("[7/9] Launching Replicator on http://localhost:8003 ...")
    rep_env = env_base.copy()
    rep_env["PORT"] = "8003"
    rep_env["CONTROLLER_URL"] = "http://127.0.0.1:8000"
    rep_env["REGION_A_URL"] = "http://127.0.0.1:8001"
    rep_env["REGION_B_URL"] = "http://127.0.0.1:8002"
    rep_env["REGION_C_URL"] = "http://127.0.0.1:8004"
    rep_env["REGION_D_URL"] = "http://127.0.0.1:8005"
    rep_env["REGION_E_URL"] = "http://127.0.0.1:8006"
    p_rep = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "replication_worker.src.main:app", "--host", "0.0.0.0", "--port", "8003"],
        cwd=str(WORKSPACE),
        env=rep_env,
    )
    processes.append(("Replicator", p_rep))

    # 8. API Gateway
    print("[8/9] Launching API Gateway on http://localhost:8080 ...")
    gw_env = env_base.copy()
    gw_env["PORT"] = "8080"
    gw_env["CONTROLLER_URL"] = "http://127.0.0.1:8000"
    gw_env["REGION_A_URL"] = "http://127.0.0.1:8001"
    gw_env["REGION_B_URL"] = "http://127.0.0.1:8002"
    gw_env["REGION_C_URL"] = "http://127.0.0.1:8004"
    gw_env["REGION_D_URL"] = "http://127.0.0.1:8005"
    gw_env["REGION_E_URL"] = "http://127.0.0.1:8006"
    gw_env["DEFAULT_TARGET"] = "region-a"
    gw_env["TELEMETRY_EXPORT_ENABLED"] = "true"
    gw_env["TELEMETRY_EXPORT_INTERVAL_SECONDS"] = "1.0"
    p_gw = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "gateway.src.main:app", "--host", "0.0.0.0", "--port", "8080"],
        cwd=str(WORKSPACE),
        env=gw_env,
    )
    processes.append(("API Gateway", p_gw))

    # 9. Frontend Vite Dev Server
    print("[9/9] Launching Frontend UI on http://localhost:5173 ...")
    frontend_dir = WORKSPACE / "FailoverLab - Frontend"
    npm_bin = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    p_fe = subprocess.Popen(
        [npm_bin, "run", "dev", "--", "--host", "0.0.0.0"],
        cwd=str(frontend_dir),
    )
    processes.append(("Frontend UI", p_fe))

    print("\n" + "=" * 75)
    print("  FAILOVERLAB IS FULLY ACTIVE AND RUNNING!")
    print("=" * 75)
    print("  - Online Technology Storefront: http://localhost:5173/shop")
    print("  - Controller Observability UI:  http://localhost:5173/controller")
    print("  - Distributed Operations Console: http://localhost:5173/")
    print("  - Gateway API & Metrics:        http://localhost:8080/api/traffic/telemetry")
    print("  - Controller Traffic APIs:      http://localhost:8000/api/v1/traffic/summary")
    print("=" * 75)
    print("Press CTRL+C to terminate all services.\n")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
