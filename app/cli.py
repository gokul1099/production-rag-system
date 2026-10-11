import os
import sys
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
