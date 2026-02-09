from fastapi import FastAPI
from meeting_prep.agents.meeting_prep.api.router import router as meeting_prep_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Meeting Prep Gamma Agent",
        version="1.0.0",
        description="Gamma-ready Meeting Brief generation agent.",
    )

    app.include_router(meeting_prep_router)

    return app


app = create_app()
