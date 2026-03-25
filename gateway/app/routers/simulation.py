"""Simulation API router."""

from fastapi import APIRouter

from app.schemas import SimulationRequest, SimulationResponse
from app.services.orchestrator import run_simulation

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])


@router.post("/run", response_model=SimulationResponse)
async def run(request: SimulationRequest):
    """Run a full simulation: ML forecast → optimize → grid validate."""
    return await run_simulation(request)
