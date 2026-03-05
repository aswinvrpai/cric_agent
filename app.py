"""
CricClubs AI Agent — FastAPI Web Application
=============================================
SETUP:
    pip install fastapi uvicorn jinja2 python-multipart groq playwright beautifulsoup4
    playwright install chromium

RUN:
    uvicorn main:app --reload --port 8000
    Then open: http://localhost:8000
"""
import os
import json
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from exception import CustomException
from dotenv import load_dotenv
load_dotenv()  # reads .env and loads it into environment

# Logger
from logger.logger import setup_logger, log_file
logger = setup_logger("mainapp", log_file)

from uvicorn import run as app_run
import uvicorn

from pathlib import Path

import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Helper to run async playwright code safely from FastAPI
def run_in_new_loop(coro):
    """Run a coroutine in a fresh event loop in a separate thread."""
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        return future.result()

# Add this near the top, after imports
BASE_DIR = Path(__file__).resolve().parent

from cric_agent import (
    CricketAnalyst,
    scrape_urls,
    generate_match_report,
    generate_league_report,
    generate_multi_match_report,
    CLUB_ID, LEAGUE_ID, BASE_URL,
)

# ── App setup ────────────────────────────────────────────
app = FastAPI(title="CricClubs AI Agent")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── Global state (simple in-memory session) ──────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
analyst: Optional[CricketAnalyst] = None
scraped_data: dict = {}
session_report: str = ""


def get_analyst() -> CricketAnalyst:
    global analyst
    if analyst is None:
        analyst = CricketAnalyst(api_key=GROQ_API_KEY, model="llama-3.3-70b-versatile")
    return analyst


# ── Routes ───────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/scorecard", response_class=JSONResponse)
async def api_scorecard(match_id: str = Form(...)):
    """Scrape a single match and generate a report."""
    global scraped_data, session_report, analyst
    
    # Logging;
    logger.info("Enter api_scorecard")
    
    try:
        urls = {
            "scorecard": f"{BASE_URL}/viewScorecard.do?matchId={match_id}&clubId={CLUB_ID}",
        }
        
        # Log
        logger.info(f"urls passed:{urls}")
        
        # scraped_data = await scrape_urls(urls)
        scraped_data = await asyncio.get_event_loop().run_in_executor(
            None, lambda: run_in_new_loop(scrape_urls(urls))
        )
        logger.info(f"scraped_data:{scraped_data}")

        # Reset analyst conversation for new match
        analyst = get_analyst()
        report = generate_match_report(analyst, scraped_data)
        analyst.start_conversation(scraped_data)
        session_report = report

        return {"status": "ok", "report": report, "match_id": match_id}

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/league", response_class=JSONResponse)
async def api_league():
    """Scrape league overview and generate report."""
    global scraped_data, session_report, analyst

    try:
        urls = {
            "league_results": f"{BASE_URL}/leagueResults.do?league={LEAGUE_ID}&clubId={CLUB_ID}",
            "points_table":   f"{BASE_URL}/leaguePointstable.do?league={LEAGUE_ID}&clubId={CLUB_ID}",
            "batting_table":  f"{BASE_URL}/leagueBatting.do?league={LEAGUE_ID}&clubId={CLUB_ID}",
            "bowling_table":  f"{BASE_URL}/leagueBowling.do?league={LEAGUE_ID}&clubId={CLUB_ID}",
        }
        scraped_data = await scrape_urls(urls)

        analyst = get_analyst()
        report = generate_league_report(analyst, scraped_data)
        analyst.start_conversation(scraped_data)
        session_report = report

        return {"status": "ok", "report": report}

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/multi", response_class=JSONResponse)
async def api_multi(match_ids: str = Form(...)):
    """Scrape multiple matches and compare."""
    global scraped_data, session_report, analyst

    try:
        ids = [m.strip() for m in match_ids.split(",") if m.strip()]
        urls = {
            f"match_{mid}": f"{BASE_URL}/viewScorecard.do?matchId={mid}&clubId={CLUB_ID}"
            for mid in ids
        }
        scraped_data = await scrape_urls(urls)

        analyst = get_analyst()
        report = generate_multi_match_report(analyst, scraped_data, len(ids))
        analyst.start_conversation(scraped_data)
        session_report = report

        return {"status": "ok", "report": report, "match_ids": ids}

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/chat", response_class=JSONResponse)
async def api_chat(message: str = Form(...)):
    """Interactive Q&A — multi-turn conversation."""
    global analyst, scraped_data

    if not scraped_data:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "No match data loaded yet. Please run a report first."}
        )

    try:
        a = get_analyst()
        # If conversation hasn't been started yet, start it
        if not a.conversation_history:
            a.start_conversation(scraped_data)
        reply = a.chat(message)
        return {"status": "ok", "reply": reply}

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/reset", response_class=JSONResponse)
async def api_reset():
    """Reset the session."""
    global analyst, scraped_data, session_report
    analyst = None
    scraped_data = {}
    session_report = ""
    return {"status": "ok", "message": "Session reset."}

# Run the application
if __name__ == "__main__":
    APP_HOST = "127.0.0.1"
    APP_PORT = "8080"
    uvicorn.run("app:app", host=APP_HOST, port=int(APP_PORT), reload=True)