"""Web Research Agent — gpt-researcher pipeline: planner→executor→publisher + trafilatura extraction + citations."""
from __future__ import annotations
import time, json, hashlib, asyncio, concurrent.futures, re
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

CACHE_DIR = Path("memory/web_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR = Path("memory/research")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

_HTTPX_AVAILABLE = False
_TRAFILATURA_AVAILABLE = False
_DDG_AVAILABLE = False

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    pass

try:
    from trafilatura import extract, fetch_url, bare_extraction
    _TRAFILATURA_AVAILABLE = True
except ImportError:
    pass

try:
    from duckduckgo_search import DDGS
    _DDG_AVAILABLE = True
except ImportError:
    pass


def _fetch_url(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch URL content using httpx (preferred) or urllib fallback."""
    if _HTTPX_AVAILABLE:
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.text
        except Exception:
            return None
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _extract_content(html: str, url: str = "") -> dict:
    """Extract clean content using trafilatura (gold standard) or fallback."""
    if _TRAFILATURA_AVAILABLE and html:
        try:
            result = bare_extraction(html, url=url, favor_precision=True, include_comments=False)
            if result and result.get("text"):
                return {
                    "title": result.get("title", ""),
                    "text": result["text"][:15000],
                    "date": result.get("date", ""),
                    "author": result.get("author", ""),
                    "site": result.get("hostname", ""),
                }
        except Exception:
            pass
    # Fallback: basic html stripping
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.split("\n") if len(l) > 40][:200]
        return {"title": soup.title.string.strip() if soup.title else "", "text": "\n".join(lines)[:15000]}
    except ImportError:
        return {"text": re.sub(r"<[^>]+>", " ", html)[:15000]}
    except Exception:
        return {"text": ""}


class WebResearchAgent:
    """Deep research with gpt-researcher pipeline: planner→executor→publisher + citations."""

    def __init__(self):
        self._history: list[dict] = []
        self._visited: set[str] = set()

    # ── Search ─────────────────────────────────────────────────────

    def search(self, query: str, max_results: int = 8) -> dict:
        urls = []
        if _DDG_AVAILABLE:
            try:
                with DDGS() as ddgs:
                    for r in ddgs.text(query, max_results=max_results):
                        urls.append({"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")})
            except Exception:
                pass
        if not urls:
            urls = self._search_fallback(query, max_results)
        seen = set()
        unique = []
        for u in urls:
            if u["url"] and u["url"] not in seen:
                seen.add(u["url"])
                unique.append(u)
        self._history.append({"action": "search", "query": query, "results": len(unique), "time": time.time()})
        return {"query": query, "results": unique[:max_results], "total": len(unique)}

    def _search_fallback(self, query: str, max_results: int) -> list[dict]:
        urls = []
        try:
            import requests
            from bs4 import BeautifulSoup
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for r in soup.select(".result"):
                title_el = r.select_one(".result__title a")
                snippet_el = r.select_one(".result__snippet")
                if title_el:
                    urls.append({
                        "title": title_el.get_text(strip=True),
                        "url": title_el.get("href", ""),
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    })
        except Exception:
            pass
        return urls

    # ── Fetch single page ──────────────────────────────────────────

    def fetch_page(self, url: str) -> dict:
        if url in self._visited:
            return {"error": "Already visited", "url": url}
        html = _fetch_url(url)
        if not html:
            return {"url": url, "error": "Failed to fetch"}
        extracted = _extract_content(html, url)
        self._visited.add(url)
        entry = {
            "url": url,
            "title": extracted.get("title", url),
            "content": extracted.get("text", ""),
            "length": len(extracted.get("text", "")),
            "fetched_at": time.time(),
        }
        self._history.append({"action": "fetch", "url": url, "title": entry["title"], "time": time.time()})
        return entry

    def fetch_multi(self, urls: list[str], max_workers: int = 5) -> list[dict]:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self.fetch_page, u): u for u in urls}
            for future in concurrent.futures.as_completed(futures):
                r = future.result()
                if "error" not in r:
                    results.append(r)
        return results

    # ── Deep research pipeline ─────────────────────────────────────

    def research(self, topic: str, depth: int = 2, max_pages: int = 8) -> dict:
        """Full gpt-researcher pipeline: plan → execute → synthesize → report."""
        # Plan: decompose topic into sub-questions
        plan = self._plan(topic)
        # Execute: search + fetch for each sub-question
        all_pages = []
        for sq in plan["sub_questions"]:
            sr = self.search(sq, max_results=4)
            urls = [r["url"] for r in sr.get("results", []) if r.get("url")]
            pages = self.fetch_multi(urls[:max_pages // max(len(plan["sub_questions"]), 1)])
            all_pages.extend(pages)
        # Deduplicate
        seen_urls = set()
        unique_pages = []
        for p in all_pages:
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"])
                unique_pages.append(p)
        unique_pages = unique_pages[:max_pages]
        # Synthesize
        synthesis = self._synthesize(topic, unique_pages)
        report_id = hashlib.md5(f"{topic}:{time.time()}".encode()).hexdigest()[:8]
        report = {
            "id": report_id,
            "topic": topic,
            "depth": depth,
            "plan": plan,
            "pages_fetched": len(unique_pages),
            "synthesis": synthesis,
            "sources": [{"title": p["title"], "url": p["url"], "content_preview": p.get("content", "")[:200]} for p in unique_pages],
            "timestamp": time.time(),
        }
        report_path = REPORT_DIR / f"research_{report_id}.json"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return report

    def _plan(self, topic: str) -> dict:
        """Decompose a research topic into sub-questions (planner agent)."""
        # Extract key phrases as sub-topics
        words = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", topic)
        phrases = [w for w in words if len(w) > 8]
        if not phrases:
            phrases = [topic]
        sub_questions = [f"What is {phrase}?" for phrase in phrases[:4]]
        if not sub_questions:
            sub_questions = [f"Tell me about {topic}"]
        return {"main_topic": topic, "sub_questions": sub_questions, "depth": len(sub_questions)}

    def _synthesize(self, topic: str, pages: list[dict]) -> dict:
        """Synthesize multiple sources into structured findings (publisher agent)."""
        if not pages:
            return {"summary": "No pages fetched.", "sections": []}
        all_text = " ".join(p.get("content", "")[:3000] for p in pages)
        keywords = [w for w in re.findall(r"\b[A-Z][a-z]{4,}(?:\s+[A-Z][a-z]{4,}){0,2}\b", all_text) if len(w) > 8]
        keyword_counts = Counter(keywords)
        top_keywords = [kw for kw, _ in keyword_counts.most_common(12)]
        sections = []
        for kw in top_keywords:
            mentions = []
            for p in pages:
                if kw.lower() in p.get("content", "").lower():
                    mentions.append({"title": p["title"][:60], "url": p["url"]})
            if mentions:
                sections.append({
                    "topic": kw,
                    "mentioned_in": len(mentions),
                    "sources": mentions[:3],
                })
        return {
            "summary": f"Researched {len(pages)} sources. Key topics: {', '.join(top_keywords[:8])}",
            "section_count": len(sections),
            "sections": sections[:10],
        }

    # ── Q&A ────────────────────────────────────────────────────────

    def ask(self, question: str, context_urls: Optional[list[str]] = None) -> dict:
        if context_urls:
            pages = self.fetch_multi(context_urls)
        else:
            sr = self.search(question, max_results=5)
            urls = [r["url"] for r in sr.get("results", []) if r.get("url")]
            pages = self.fetch_multi(urls)
        synthesis = self._synthesize(question, pages)
        return {
            "question": question,
            "pages_consulted": len(pages),
            "synthesis": synthesis,
            "sources": [p["url"] for p in pages],
        }

    # ── Utility ────────────────────────────────────────────────────

    def stats(self) -> dict:
        return {"visited": len(self._visited), "history": len(self._history)}

    def history(self, limit: int = 20) -> list[dict]:
        return self._history[-limit:]

    def clear(self):
        self._visited.clear()
        self._history.clear()


researcher = WebResearchAgent()
