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
import signal
import subprocess
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
PYTHON_EXE = WORKSPACE / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

processes = []


def cleanup():
    print("\nShutting down all FailoverLab services...")
    for name, p in processes:
        try:
            p.terminate()
            p.wait(timeout=2.0)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        print(f"  -> {name} stopped.")
    print("All services stopped.")


def main():
    print("=" * 75)
    print("  STARTING FAILOVERLAB FULL SYSTEM STACK")
    print("=" * 75)

    env_base = os.environ.copy()
    env_base["PYTHONPATH"] = str(WORKSPACE)

    # 1. Controller
    print("[1/5] Launching Controller on http://localhost:8000 ...")
    ctrl_env = env_base.copy()
    ctrl_env["PORT"] = "8000"
    ctrl_env["DATABASE_URL"] = "sqlite+aiosqlite:///./controller.db"
    ctrl_env["GATEWAY_URL"] = "http://127.0.0.1:8080"
    ctrl_env["REGION_A_URL"] = "http://127.0.0.1:8001"
    ctrl_env["REGION_B_URL"] = "http://127.0.0.1:8002"
    ctrl_env["SIMULATION_MODE"] = "false"
    p_ctrl = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "controller.src.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(WORKSPACE),
        env=ctrl_env,
    )
    processes.append(("Controller", p_ctrl))

    # 2. Region A
    print("[2/5] Launching Region A (Mumbai) on http://localhost:8001 ...")
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

    # 3. Region B
    print("[3/5] Launching Region B (Singapore) on http://localhost:8002 ...")
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

    # 4. Gateway
    print("[4/5] Launching API Gateway on http://localhost:8080 ...")
    gw_env = env_base.copy()
    gw_env["PORT"] = "8080"
    gw_env["CONTROLLER_URL"] = "http://127.0.0.1:8000"
    gw_env["REGION_A_URL"] = "http://127.0.0.1:8001"
    gw_env["REGION_B_URL"] = "http://127.0.0.1:8002"
    gw_env["DEFAULT_TARGET"] = "region-a"
    gw_env["TELEMETRY_EXPORT_ENABLED"] = "true"
    gw_env["TELEMETRY_EXPORT_INTERVAL_SECONDS"] = "1.0"
    p_gw = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "gateway.src.main:app", "--host", "0.0.0.0", "--port", "8080"],
        cwd=str(WORKSPACE),
        env=gw_env,
    )
    processes.append(("API Gateway", p_gw))

    # 5. Frontend Vite Dev Server
    print("[5/5] Launching Frontend UI on http://localhost:5173 ...")
    frontend_dir = WORKSPACE / "FailoverLab - Frontend"
    p_fe = subprocess.Popen(
        ["npm.cmd", "run", "dev", "--", "--host", "0.0.0.0"],
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
