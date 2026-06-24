from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field

import logging
from datetime import datetime
from info.router import router as info_router
from historical.router import router as historical_router
from live.router import router as live_router





# CURRENT_SESSION_ID = 684
# CURRENT_SESSION_ID = 319

app = FastAPI(title="f1pace API")
app.include_router(info_router)
app.include_router(historical_router)
app.include_router(live_router)

