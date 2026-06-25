from fastapi import FastAPI
from info.router import router as info_router
from historical.router import router as historical_router
from live.router import router as live_router
from emulation.router import router as emulation_router


app = FastAPI(title="f1pace API")
app.include_router(info_router)
app.include_router(historical_router)
app.include_router(live_router)
app.include_router(emulation_router)
