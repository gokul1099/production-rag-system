import os
import signal
import subprocess
import sys
import time
import uvicorn


def run_api():
    """Start the FastAPI backend service."""
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)


def run_gateway():
    """Start the API Gateway service."""
    port = int(os.getenv("GATEWAY_PORT", "8001"))
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=port, reload=True)


def run_ui():
    """Start the Streamlit UI."""
    from streamlit.web import cli as stcli

    port = os.getenv("STREAMLIT_SERVER_PORT", "8501")
    sys.argv = ["streamlit", "run", "ui/app.py", f"--server.port={port}"]
    sys.exit(stcli.main())


def run_all():
    """
    Start all servers (Backend API, Gateway, and Streamlit UI) concurrently in local Python processes.
    Press Ctrl+C to stop all servers gracefully.
    """
    print("🚀 Starting all services locally (API: 8000, Gateway: 8001, Streamlit UI: 8501)...")
    python_bin = sys.executable

    commands = [
        ("Backend API", [python_bin, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]),
        ("Gateway", [python_bin, "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]),
        ("Streamlit UI", [python_bin, "-m", "streamlit", "run", "ui/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]),
    ]

    processes = []
    try:
        for name, cmd in commands:
            print(f"  ▶️ Launching {name}...")
            p = subprocess.Popen(cmd)
            processes.append(p)
            time.sleep(1)

        print("\n✅ All servers running! Press Ctrl+C to terminate all services.\n")
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"⚠️ A service process exited with code {p.returncode}")
                    sys.exit(p.returncode)
    except KeyboardInterrupt:
        print("\n🛑 Stopping all services...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.wait()
        print("👋 All services stopped.")


def run_docker():
    """
    Build and start all services locally as Docker containers using docker-compose.
    """
    print("🐳 Starting all containers via docker-compose...")
    cmd = ["docker", "compose", "up", "--build"]
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n🛑 Stopping all Docker containers...")
        subprocess.run(["docker", "compose", "down"])
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
