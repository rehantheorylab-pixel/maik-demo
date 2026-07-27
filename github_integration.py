"""GitHub Integration — full API access: repos, issues, PRs, gists, search, code.

Uses PyGithub if available, otherwise raw requests.
"""
from __future__ import annotations
import json, os, time, base64
from typing import Optional

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API = "https://api.github.com"

_HAS_PYGITHUB = False
try:
    from github import Github, GithubException
    _HAS_PYGITHUB = True
except ImportError:
    pass


class GitHubIntegration:
    """Full GitHub integration: repos, issues, PRs, gists, search, code.

    Uses PyGithub (richer) or raw requests (always available).
    """

    def __init__(self, token: str = ""):
        self._token = token or GITHUB_TOKEN
        self._gh = None
        self._user = None
        self._cache: dict = {}
        self._history: list[dict] = []
        if _HAS_PYGITHUB and self._token:
            try:
                self._gh = Github(self._token)
                self._user = self._gh.get_user()
            except Exception:
                pass

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    @property
    def is_authenticated(self) -> bool:
        return self._gh is not None and self._user is not None

    # ── User ───────────────────────────────────────────────────────

    def get_user(self) -> dict:
        if self.is_authenticated:
            u = self._user
            return {
                "login": u.login, "name": u.name, "email": u.email,
                "bio": u.bio, "public_repos": u.public_repos,
                "followers": u.followers, "following": u.following,
                "avatar_url": u.avatar_url, "url": u.html_url,
            }
        # Fallback to API
        return self._get(f"/user")

    # ── Repos ──────────────────────────────────────────────────────

    def list_repos(self, username: str = "", sort: str = "updated") -> list[dict]:
        endpoint = f"/users/{username}/repos" if username else "/user/repos"
        data = self._get(endpoint, {"sort": sort, "per_page": 50})
        if isinstance(data, list):
            return [
                {
                    "name": r.get("name", ""), "full_name": r.get("full_name", ""),
                    "description": r.get("description", ""), "language": r.get("language"),
                    "stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0),
                    "url": r.get("html_url", ""), "private": r.get("private", False),
                    "updated_at": r.get("updated_at", ""),
                }
                for r in data
            ]
        return []

    def get_repo(self, owner: str, repo: str) -> dict:
        endpoint = f"/repos/{owner}/{repo}"
        data = self._get(endpoint)
        if isinstance(data, dict):
            return {
                "name": data.get("full_name", ""), "description": data.get("description", ""),
                "language": data.get("language"), "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0), "issues": data.get("open_issues_count", 0),
                "url": data.get("html_url", ""), "license": data.get("license", {}).get("spdx_id", ""),
                "default_branch": data.get("default_branch", "main"),
                "topics": data.get("topics", []),
            }
        return {}

    def search_repos(self, query: str, limit: int = 10) -> list[dict]:
        endpoint = "/search/repositories"
        data = self._get(endpoint, {"q": query, "per_page": limit, "sort": "stars"})
        items = data.get("items", [])
        return [
            {
                "name": r.get("full_name", ""), "description": r.get("description", ""),
                "language": r.get("language"), "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0), "url": r.get("html_url", ""),
            }
            for r in items
        ]

    def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> Optional[str]:
        endpoint = f"/repos/{owner}/{repo}/contents/{path}"
        data = self._get(endpoint, {"ref": branch})
        if isinstance(data, dict) and data.get("content"):
            try:
                return base64.b64decode(data["content"]).decode()
            except Exception:
                return data.get("content", "")
        return None

    def list_files(self, owner: str, repo: str, path: str = "", branch: str = "main") -> list[dict]:
        endpoint = f"/repos/{owner}/{repo}/contents/{path}"
        data = self._get(endpoint, {"ref": branch})
        if isinstance(data, list):
            return [
                {"name": f.get("name", ""), "type": f.get("type", ""),
                 "path": f.get("path", ""), "size": f.get("size", 0),
                 "url": f.get("html_url", "")}
                for f in data
            ]
        return []

    # ── Issues ─────────────────────────────────────────────────────

    def list_issues(self, owner: str, repo: str, state: str = "open", limit: int = 20) -> list[dict]:
        endpoint = f"/repos/{owner}/{repo}/issues"
        data = self._get(endpoint, {"state": state, "per_page": limit, "sort": "updated"})
        if isinstance(data, list):
            return [
                {
                    "number": i.get("number", 0), "title": i.get("title", ""),
                    "state": i.get("state", ""), "user": i.get("user", {}).get("login", ""),
                    "labels": [l.get("name", "") for l in i.get("labels", [])],
                    "comments": i.get("comments", 0),
                    "body": (i.get("body") or "")[:500],
                    "url": i.get("html_url", ""), "created_at": i.get("created_at", ""),
                }
                for i in data
            ]
        return []

    def create_issue(self, owner: str, repo: str, title: str, body: str = "",
                     labels: list[str] = None) -> dict:
        if self.is_authenticated:
            try:
                r = self._gh.get_repo(f"{owner}/{repo}")
                issue = r.create_issue(title=title, body=body, labels=labels or [])
                self._history.append({"action": "create_issue", "repo": f"{owner}/{repo}", "title": title})
                return {"number": issue.number, "url": issue.html_url, "title": issue.title}
            except Exception as e:
                return {"error": str(e)}
        endpoint = f"/repos/{owner}/{repo}/issues"
        data = self._post(endpoint, {"title": title, "body": body, "labels": labels or []})
        self._history.append({"action": "create_issue", "repo": f"{owner}/{repo}", "title": title})
        return {"number": data.get("number", 0), "url": data.get("html_url", ""), "title": title} if isinstance(data, dict) else {"error": "Failed"}

    def close_issue(self, owner: str, repo: str, number: int) -> dict:
        endpoint = f"/repos/{owner}/{repo}/issues/{number}"
        data = self._patch(endpoint, {"state": "closed"})
        return {"number": number, "state": "closed"} if isinstance(data, dict) else {"error": "Failed"}

    # ── Pull Requests ──────────────────────────────────────────────

    def list_pull_requests(self, owner: str, repo: str, state: str = "open", limit: int = 10) -> list[dict]:
        endpoint = f"/repos/{owner}/{repo}/pulls"
        data = self._get(endpoint, {"state": state, "per_page": limit})
        if isinstance(data, list):
            return [
                {
                    "number": pr.get("number", 0), "title": pr.get("title", ""),
                    "state": pr.get("state", ""), "user": pr.get("user", {}).get("login", ""),
                    "body": (pr.get("body") or "")[:300],
                    "merged": pr.get("merged", False),
                    "url": pr.get("html_url", ""),
                    "created_at": pr.get("created_at", ""),
                }
                for pr in data
            ]
        return []

    def create_pull_request(self, owner: str, repo: str, title: str, head: str,
                            base: str = "main", body: str = "") -> dict:
        endpoint = f"/repos/{owner}/{repo}/pulls"
        data = self._post(endpoint, {"title": title, "head": head, "base": base, "body": body})
        self._history.append({"action": "create_pr", "repo": f"{owner}/{repo}", "title": title})
        return {"number": data.get("number", 0), "url": data.get("html_url", ""), "title": title} if isinstance(data, dict) else {"error": "Failed"}

    def merge_pull_request(self, owner: str, repo: str, number: int) -> dict:
        if self.is_authenticated:
            try:
                r = self._gh.get_repo(f"{owner}/{repo}")
                pr = r.get_pull(number)
                pr.merge()
                return {"number": number, "merged": True}
            except Exception as e:
                return {"error": str(e)}
        endpoint = f"/repos/{owner}/{repo}/pulls/{number}/merge"
        data = self._put(endpoint)
        return {"number": number, "merged": data.get("merged", False)} if isinstance(data, dict) else {"error": "Failed"}

    # ── Gists ──────────────────────────────────────────────────────

    def list_gists(self, username: str = "") -> list[dict]:
        endpoint = f"/users/{username}/gists" if username else "/gists"
        data = self._get(endpoint, {"per_page": 20})
        if isinstance(data, list):
            return [
                {
                    "id": g.get("id", ""), "description": g.get("description", ""),
                    "files": list(g.get("files", {}).keys()),
                    "url": g.get("html_url", ""), "public": g.get("public", False),
                }
                for g in data
            ]
        return []

    def create_gist(self, files: dict[str, str], description: str = "",
                    public: bool = False) -> dict:
        endpoint = "/gists"
        gist_files = {name: {"content": content} for name, content in files.items()}
        data = self._post(endpoint, {"description": description, "public": public, "files": gist_files})
        return {"id": data.get("id", ""), "url": data.get("html_url", "")} if isinstance(data, dict) else {"error": "Failed"}

    # ── Search Code ────────────────────────────────────────────────

    def search_code(self, query: str, limit: int = 10) -> list[dict]:
        endpoint = "/search/code"
        data = self._get(endpoint, {"q": query, "per_page": limit})
        items = data.get("items", [])
        return [
            {
                "name": i.get("name", ""), "path": i.get("path", ""),
                "repo": i.get("repository", {}).get("full_name", ""),
                "url": i.get("html_url", ""),
            }
            for i in items
        ]

    # ── Raw API ────────────────────────────────────────────────────

    def _headers(self) -> dict:
        h = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MAIK-GitHub-Integration",
        }
        if self._token:
            h["Authorization"] = f"token {self._token}"
        return h

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict | list:
        import requests
        url = f"{GITHUB_API}{endpoint}"
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"GitHub API error {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def _post(self, endpoint: str, data: dict) -> dict:
        import requests
        url = f"{GITHUB_API}{endpoint}"
        try:
            resp = requests.post(url, headers=self._headers(), json=data, timeout=15)
            if resp.status_code in (200, 201):
                return resp.json()
            return {"error": f"GitHub API error {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def _patch(self, endpoint: str, data: dict) -> dict:
        import requests
        url = f"{GITHUB_API}{endpoint}"
        try:
            resp = requests.patch(url, headers=self._headers(), json=data, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"GitHub API error {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def _put(self, endpoint: str) -> dict:
        import requests
        url = f"{GITHUB_API}{endpoint}"
        try:
            resp = requests.put(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"GitHub API error {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    # ── Utils ──────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Usage statistics."""
        total_actions = len(self._history)
        return {
            "authenticated": self.is_authenticated,
            "has_token": self.has_token,
            "history_count": total_actions,
            "recent_actions": self._history[-10:],
        }

    def history(self, limit: int = 20) -> list[dict]:
        return self._history[-limit:]


github = GitHubIntegration()
