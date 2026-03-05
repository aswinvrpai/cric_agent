"""
╔══════════════════════════════════════════════════════╗
║         CricClubs End-to-End AI Agent                ║
║  Scrape → Analyse → Report → Interactive Q&A         ║
╚══════════════════════════════════════════════════════╝

SETUP:
    pip install playwright anthropic beautifulsoup4
    playwright install chromium
    set ANTHROPIC_API_KEY=your_key_here   (Windows)
    export ANTHROPIC_API_KEY=your_key     (Mac/Linux)

USAGE:
    python cricclubs_agent.py
    python cricclubs_agent.py --mode scorecard --match-id 6178
    python cricclubs_agent.py --mode league
    python cricclubs_agent.py --mode multi --match-ids 6178 6088 6050
"""

import os
import json
import asyncio
import argparse
from datetime import datetime
from bs4 import BeautifulSoup
# import anthropic
from playwright.async_api import async_playwright

# Setup Logger;
from logger.logger import setup_logger,log_file
logger = setup_logger("cric_agent", log_file)


# ══════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════

# https://cricclubs.com/cricketorjp/leagueResults.do?league=546&clubId=21278

CLUB_ID   = "21278" # Japan Cricket Association (JCA)
LEAGUE_ID = "546" # Japan Cricket League (JCL) - Division 1
BASE_URL  = "https://cricclubs.com/cricketorjp"

# ══════════════════════════════════════════════════════
# STEP 1 — SCRAPER
# ══════════════════════════════════════════════════════

async def create_browser_context(playwright):
    """Launch a Cloudflare-friendly browser context."""
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox"],
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    return browser, context


async def scrape_page(url: str, page) -> str:
    """Fetch a CricClubs page and return clean text."""
    print(f"    Fetching: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)   # Let JS render

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    lines = [
        line for line in soup.get_text(separator="\n", strip=True).splitlines()
        if line.strip()
    ]
    return "\n".join(lines)


async def scrape_urls(urls: dict) -> dict:
    
    # Log Info;
    logger.info("Enter scrape_urls")
    
    """Scrape multiple URLs in one browser session."""
    results = {}
    async with async_playwright() as p:
        
        # Log Info;
        logger.info("Enter scrape_urls - p :{p}")
        
        browser, context = await create_browser_context(p)
        page = await context.new_page()
        
        # Log Info;
        logger.info(f"Enter scrape_urls - page : {page}")

        for name, url in urls.items():
            try:
                # print(f"  Scraping '{name}'...")
                # Log Info;
                logger.info(f"  Scraping '{name}'...")
                text = await scrape_page(url, page)
                results[name] = {"url": url, "content": text, "status": "ok"}
                # print(f"    Got {len(text):,} characters")
                logger.info(f"    Got {len(text):,} characters")
            except Exception as e:
                # print(f"    Failed: {e}")
                logger.info(f"    Failed: {e}")
                results[name] = {"url": url, "content": "", "status": f"error: {e}"}

        await browser.close()
    return results


# ══════════════════════════════════════════════════════
# STEP 2 — CLAUDE ANALYSIS ENGINE
# ══════════════════════════════════════════════════════

# pip install groq
from groq import Groq
class CricketAnalyst:
    """Wrapper around Groq for cricket-specific analysis."""

    SYSTEM_PROMPT = """You are an expert cricket analyst covering the Japan Cricket League (JCL).
        You receive raw scraped text from CricClubs match pages. Your job is to:
        - Extract meaningful cricket data (scores, wickets, overs, player stats)
        - Ignore all page boilerplate, navigation text, buttons, and UI noise
        - Write clear, engaging, accurate cricket analysis
        - Use proper cricket terminology
        - Match date are given in the format of day/month/year. So give the match date accordingly.
        - Be concise but comprehensive"""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.client = Groq(api_key=api_key)
        self.model = model
        self.conversation_history = []

    # Add this cleaning function
    JUNK_PHRASES = [
        "Loading", "Confirmation Message", "Delete", "Cancel", "Lock", "Unlock",
        "Terms and Conditions", "Rendering data", "Ball By Ball", "Over By Over",
        "Charts", "Insert title here", "Home", "null", "Message !!"
    ]

    def clean_scraped_text(self,text: str) -> str:
        lines = text.splitlines()
        cleaned = [
            line for line in lines
            if line.strip()
            and not any(junk in line for junk in self.JUNK_PHRASES)
            and len(line.strip()) > 2        # removes single-char lines
        ]
        return "\n".join(cleaned)


    # Then use it in _build_context:
    def _build_context(self, scraped_data: dict) -> str:
        parts = []
        for name, data in scraped_data.items():
            if data["status"] == "ok" and data["content"]:
                cleaned = self.clean_scraped_text(data["content"])
                parts.append(
                    f"=== {name.upper().replace('_', ' ')} ===\n"
                    f"Source: {data['url']}\n\n"
                    f"{cleaned[:5000]}"   # smaller slice of already-clean text
                )
        return "\n\n".join(parts)

    def analyse(self, scraped_data: dict, prompt: str) -> str:
        """Single-turn analysis."""
        context = self._build_context(scraped_data)
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user",   "content": f"SCRAPED DATA:\n\n{context}\n\n---\n\n{prompt}"}
            ]
        )
        return response.choices[0].message.content

    def start_conversation(self, scraped_data: dict):
        """Initialise conversation history with scraped context."""
        context = self._build_context(scraped_data)
        self.conversation_history = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": (
                    f"Here is the cricket data for our conversation:\n\n{context}\n\n"
                    "I will ask you questions about this data."
                )
            },
            {
                "role": "assistant",
                "content": "Got it! I have reviewed the cricket data. Ask me anything."
            }
        ]

    def chat(self, user_message: str) -> str:
        """Multi-turn conversation — remembers previous questions."""
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1500,
            messages=self.conversation_history
        )
        reply = response.choices[0].message.content
        self.conversation_history.append({
            "role": "assistant",
            "content": reply
        })
        return reply
# ══════════════════════════════════════════════════════
# STEP 3 — REPORT GENERATORS
# ══════════════════════════════════════════════════════

def generate_match_report(analyst: CricketAnalyst, scraped_data: dict) -> str:
    prompt = """Generate a detailed match report with these sections:
When the scoreboard is scraped. Data may be in the below form:
Abhishek Anand c T Ono b N Tomizawa 103	83	8	7	124.10 - Here batsman name is 'Abhishek Anand', 
caught by 'T Ono' bowled by 'N Tomizawa', runs scored '103', balls faced '83', number of fours '8', number of sixes '7', strike rate is '124.10'.
Make sure the scoreboard scraped data is read accurately as above.
1. MATCH OVERVIEW — Result, venue, date, toss decision,In the first paragraph write the major summary of the match in bold and big letters. For eg. Tigers beat Falcons by 72 runs.
2. FIRST INNINGS — Top scorers, key partnerships, bowling highlights
3. SECOND INNINGS — Chase/defence narrative, key moments
4. PLAYER OF THE MATCH — Why they deserved it with stats
5. KEY STATS — Top scorer, best bowling figures, extras
6. MATCH VERDICT — 2-3 sentence summary of how the match unfolded

Write like a professional cricket journalist. Be specific with numbers."""
    return analyst.analyse(scraped_data, prompt)


def generate_league_report(analyst: CricketAnalyst, scraped_data: dict) -> str:
    prompt = """Generate a league overview report with:

1. RECENT RESULTS — Summary of latest matches
2. POINTS TABLE — Current standings with teams,matches(PLD), wins(WON), losses(LOST),No result(N/R), tie(Tie) and points
3. FORM GUIDE — Which teams are in good or poor form
4. TOP PERFORMERS — Standout batsmen and bowlers this season
5. SEASON OUTLOOK — Which teams look strong for the title
6. BOWLING PERFORMANCE — Which bowlers have taken the most wickets and best averages and total number of wickets(WKTS). Give the top 5 bowlers with their stats.
7. BATTING PERFORMANCE — Which batsmen have scored the most runs and best averages. Give the top 5 batsmen with their stats."""
    return analyst.analyse(scraped_data, prompt)


def generate_multi_match_report(analyst: CricketAnalyst, scraped_data: dict, count: int) -> str:
    prompt = f"""You have data from {count} matches. Provide:

1. RESULTS SUMMARY — Brief result for each match
2. STAR PERFORMERS — Top 3 batsmen and top 3 bowlers across all matches
3. TEAM FORM — How each team performed
4. MATCH OF THE ROUND — Most exciting match and why
5. KEY TRENDS — Patterns or observations across the matches"""
    return analyst.analyse(scraped_data, prompt)


def save_report(report: str, filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(report)
    print(f"  Report saved to: {filename}")


# ══════════════════════════════════════════════════════
# STEP 4 — INTERACTIVE Q&A
# ══════════════════════════════════════════════════════

def interactive_qa(analyst: CricketAnalyst, scraped_data: dict):
    """Multi-turn conversational Q&A about the scraped data."""
    analyst.start_conversation(scraped_data)

    print("\n" + "=" * 55)
    print("  INTERACTIVE Q&A")
    print("  Ask anything about the match/league data.")
    print("  Example questions:")
    print("    > Who was the best bowler?")
    print("    > How many extras did each team concede?")
    print("    > Give me a fantasy cricket XI from this match")
    print("    > Which team has the best net run rate?")
    print("  Commands: 'save' to save log | 'quit' to exit")
    print("=" * 55)
    
    import sys
    sys.stdout.flush()

    conversation_log = []

    while True:
        try:
            user_input = input("\n  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("\n  Goodbye!")
            break

        if user_input.lower() == "save":
            log_file = f"qa_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(log_file, "w", encoding="utf-8") as f:
                for entry in conversation_log:
                    f.write(f"Q: {entry['q']}\nA: {entry['a']}\n\n")
            print(f"  Saved conversation to: {log_file}")
            continue

        reply = analyst.chat(user_input)
        print(f"\n  Claude: {reply}")
        conversation_log.append({"q": user_input, "a": reply})


# ══════════════════════════════════════════════════════
# STEP 5 — AGENT MODES
# ══════════════════════════════════════════════════════

async def mode_scorecard(match_id: str):
    """Single match: scrape + report + Q&A."""
    print(f"\n{'='*55}")
    print(f"  MODE: Single Match Report  |  Match ID: {match_id}")
    print(f"{'='*55}")

    urls = {
        "scorecard":      f"{BASE_URL}/viewScorecard.do?matchId={match_id}&clubId={CLUB_ID}",
        "full_scorecard": f"{BASE_URL}/fullScorecard.do?matchId={match_id}&clubId={CLUB_ID}",
    }

    print("\n[1/3] Scraping match data...")
    scraped_data = await scrape_urls(urls)

    # Save raw data for debugging
    with open(f"raw_{match_id}.json", "w", encoding="utf-8") as f:
        json.dump(scraped_data, f, indent=2, ensure_ascii=False)

    print("\n[2/3] Generating match report with Claude...")
    
    # Cricket Analyst;
    analyst = CRICKET_ANALYST_OBJ
    
    report = generate_match_report(analyst, scraped_data)

    print("\n" + "=" * 55)
    print("  MATCH REPORT")
    print("=" * 55)
    print(report)
    save_report(report, f"match_{match_id}_report.txt")

    print("\n[3/3] Starting interactive Q&A...")
    interactive_qa(analyst, scraped_data)


async def mode_league():
    """League overview: scrape + report + Q&A."""
    print(f"\n{'='*55}")
    print(f"  MODE: League Overview")
    print(f"{'='*55}")

    urls = {
        "league_results": f"{BASE_URL}/leagueResults.do?league={LEAGUE_ID}&clubId={CLUB_ID}",
        "points_table":   f"{BASE_URL}/leaguePointstable.do?league={LEAGUE_ID}&clubId={CLUB_ID}",
        "batting_table":  f"{BASE_URL}/leagueBatting.do?league={LEAGUE_ID}&clubId={CLUB_ID}",
        "bowling_table":  f"{BASE_URL}/leagueBowling.do?league={LEAGUE_ID}&clubId={CLUB_ID}",
    }

    print("\n[1/3] Scraping league data...")
    scraped_data = await scrape_urls(urls)

    with open("raw_league.json", "w", encoding="utf-8") as f:
        json.dump(scraped_data, f, indent=2, ensure_ascii=False)

    print("\n[2/3] Generating league report with Claude...")
    analyst = CRICKET_ANALYST_OBJ
    report = generate_league_report(analyst, scraped_data)

    print("\n" + "=" * 55)
    print("  LEAGUE REPORT")
    print("=" * 55)
    # print(report)
    save_report(report, "league_report.txt")

    print("\n[3/3] Starting interactive Q&A...")
    interactive_qa(analyst, scraped_data)


async def mode_multi(match_ids: list):
    """Multiple matches: scrape + compare + Q&A."""
    print(f"\n{'='*55}")
    print(f"  MODE: Multi-Match Analysis  |  Matches: {', '.join(match_ids)}")
    print(f"{'='*55}")

    urls = {
        f"match_{mid}": f"{BASE_URL}/viewScorecard.do?matchId={mid}&clubId={CLUB_ID}"
        for mid in match_ids
    }

    print("\n[1/3] Scraping all matches...")
    scraped_data = await scrape_urls(urls)

    with open("raw_multi.json", "w", encoding="utf-8") as f:
        json.dump(scraped_data, f, indent=2, ensure_ascii=False)

    print("\n[2/3] Generating comparative analysis with Claude...")
    analyst = CRICKET_ANALYST_OBJ
    report = generate_multi_match_report(analyst, scraped_data, len(match_ids))

    print("\n" + "=" * 55)
    print("  MULTI-MATCH ANALYSIS")
    print("=" * 55)
    print(report)
    save_report(report, "multi_match_report.txt")

    print("\n[3/3] Starting interactive Q&A...")
    interactive_qa(analyst, scraped_data)


# ══════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(description="CricClubs AI Agent")
    parser.add_argument(
        "--mode",
        choices=["scorecard", "league", "multi"],
        default="scorecard",
        help="Agent mode (default: scorecard)"
    )
    parser.add_argument("--match-id",  default="6178",
                        help="Match ID for scorecard mode")
    parser.add_argument("--match-ids", nargs="+", default=["6178", "6088"],
                        help="Multiple match IDs for multi mode")
    return parser.parse_args()


async def main():
    args = parse_args()

    print("\n+------------------------------------------+")
    print("|       CricClubs AI Agent                 |")
    print("|  Scrape -> Analyse -> Report -> Q&A      |")
    print("+------------------------------------------+")

    if args.mode == "scorecard":
        await mode_scorecard(args.match_id)
    elif args.mode == "league":
        await mode_league()
    elif args.mode == "multi":
        await mode_multi(args.match_ids)


if __name__ == "__main__":
    
    # Good fast Groq models to choose from:
    # "llama-3.3-70b-versatile"   ← best quality, recommended
    # "llama-3.1-8b-instant"      ← fastest, lower quality
    # "gemma2-9b-it"              ← lightweight option
    GROQ_API_KEY = "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"
    CRICKET_ANALYST_OBJ = CricketAnalyst(api_key=GROQ_API_KEY, model="llama-3.3-70b-versatile")
    
    asyncio.run(main())