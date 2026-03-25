#!/bin/bash
# Start both the API gateway and dashboard in the same container
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true &
wait -n
