import os
import re
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, abort, redirect, render_template, request, session, url_for

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "development-only-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

GITHUB_API = "https://api.github.com"
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI", "http://127.0.0.1:5000/callback"
)


def github_request(path, params=None):
    token = session.get("github_token")
    if not token:
        abort(401, "Please sign in with GitHub first.")
    response = requests.get(
        f"{GITHUB_API}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        params=params,
        timeout=20,
    )
    if response.status_code == 404:
        abort(404, "Repository or resource not found, or your account cannot access it.")
    if response.status_code == 401:
        session.clear()
        abort(401, "GitHub sign-in expired. Please sign in again.")
    if response.status_code == 403:
        abort(403, "GitHub denied access or the API rate limit was reached.")
    response.raise_for_status()
    return response.json()


def parse_repo_url(value):
    """Accept github.com/owner/repo URLs or owner/repo; reject other hosts."""
    value = value.strip().rstrip("/")
    value = re.sub(r"^https?://github\.com/", "", value, flags=re.I)
    value = value.removesuffix(".git")
    parts = value.split("/")
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts):
        raise ValueError("Enter a GitHub repository URL, such as https://github.com/owner/repo")
    return parts[0], parts[1]


@app.get("/")
def home():
    if not session.get("github_token"):
        return render_template("login.html")
    return render_template("index.html", username=session.get("username"))


@app.get("/login")
def login():
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        abort(500, "GitHub sign-in is not configured on this site. Please contact the site owner.")
    state = os.urandom(24).hex()
    session["oauth_state"] = state
    query = urlencode({"client_id": GITHUB_CLIENT_ID, "redirect_uri": GITHUB_REDIRECT_URI,
                       "scope": "read:user repo", "state": state})
    return redirect(f"https://github.com/login/oauth/authorize?{query}")


@app.get("/callback")
def callback():
    if request.args.get("state") != session.pop("oauth_state", None):
        abort(400, "OAuth state did not match. Please try signing in again.")
    code = request.args.get("code")
    if not code:
        abort(400, "GitHub did not return an authorization code.")
    token_response = requests.post(
        "https://github.com/login/oauth/access_token",
        json={"client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET, "code": code,
              "redirect_uri": GITHUB_REDIRECT_URI},
        headers={"Accept": "application/json"}, timeout=20)
    token_response.raise_for_status()
    token = token_response.json().get("access_token")
    if not token:
        abort(400, "GitHub sign-in failed. Check the OAuth app configuration.")
    session.clear()
    session["github_token"] = token
    profile = requests.get("https://api.github.com/user",
                           headers={"Authorization": f"Bearer {token}"}, timeout=20)
    profile.raise_for_status()
    session["username"] = profile.json().get("login", "GitHub user")
    return redirect(url_for("home"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


def recent_push_actors(owner, repo):
    token = session.get("github_token")
    if not token:
        return {}
    try:
        response = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/events",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            params={"per_page": 100},
            timeout=20,
        )
        if not response.ok:
            return {}
        events = response.json()
    except (requests.RequestException, ValueError):
        return {}
    push_actors = {}
    for event in events:
        if event.get("type") != "PushEvent":
            continue
        actor = (event.get("actor") or {}).get("login")
        payload = event.get("payload") or {}
        if not actor:
            continue
        shas = [item.get("sha") for item in payload.get("commits", [])]
        if payload.get("head"):
            shas.append(payload["head"])
        for sha in shas:
            if sha:
                push_actors.setdefault(sha, actor)
    return push_actors


def risk_assessment(owner, repo, commit, push_actor=None):
    """A transparent demo heuristic, not a trained or predictive ML model."""
    points, reasons = 0, []
    commit_files = commit.get("files", [])
    commit_data = commit.get("commit", {})
    author_data = commit_data.get("author") or {}
    committer_data = commit_data.get("committer") or {}
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    additions = commit.get("stats", {}).get("additions", 0)
    deletions = commit.get("stats", {}).get("deletions", 0)
    changed = additions + deletions
    if changed > 500:
        points += 35
        reasons.append(f"Large change: {changed} lines added or removed.")
    elif changed > 200:
        points += 20
        reasons.append(f"Moderately large change: {changed} lines added or removed.")
    if len(commit_files) > 20:
        points += 25
        reasons.append(f"Touches {len(commit_files)} files, increasing review surface.")
    elif len(commit_files) > 10:
        points += 12
        reasons.append(f"Touches {len(commit_files)} files.")
    sensitive = [f["filename"] for f in commit_files if re.search(
        r"(^|/)(auth|security|payment|config|migration|database|db)(/|\.|$)|\.env", f["filename"], re.I)]
    if sensitive:
        points += 25
        reasons.append("Includes potentially sensitive files: " + ", ".join(sensitive[:5]))
    if not reasons:
        reasons.append("No large change or sensitive filename was detected by this basic heuristic.")
    recommendations = []
    if changed > 200:
        recommendations.append("Split this large change into smaller, focused pull requests and add tests for each behavior.")
    if len(commit_files) > 10:
        recommendations.append("Separate unrelated files by feature and request review from the owners of affected areas.")
    if sensitive:
        recommendations.append("Ask a security or data-owner reviewer to check the sensitive changes and add targeted regression tests.")
    recommendations.append("Run the automated test suite and CI checks before merging; this score is not a substitute for tests.")
    changed_file_details = []
    for index, changed_file in enumerate(commit_files):
        patch = changed_file.get("patch", "")
        changed_file_details.append({
            "filename": changed_file.get("filename", "Unknown file"),
            "status": changed_file.get("status", "modified"),
            "additions": changed_file.get("additions", 0),
            "deletions": changed_file.get("deletions", 0),
            "changes": changed_file.get("changes", 0),
            "patch": patch[:2500] if index < 12 else "",
            "patch_truncated": index < 12 and len(patch) > 2500,
        })
    score = min(points, 100)
    level = "High" if score >= 50 else "Medium" if score >= 25 else "Low"
    return {"score": score, "level": level, "reasons": reasons, "recommendations": recommendations,
            "additions": additions, "deletions": deletions, "files": len(commit_files),
            "changed_files": changed_file_details,
            "sha": commit["sha"], "message": commit_data.get("message", "(no commit message)").splitlines()[0],
            "author": author.get("login") or author_data.get("name", "Unknown"),
            "author_date": author_data.get("date", "Unknown date"),
            "committer": committer.get("login") or committer_data.get("name", "Unknown"),
            "committer_date": committer_data.get("date", "Unknown date"),
            "push_actor": push_actor,
            "url": commit["html_url"], "repo": f"{owner}/{repo}"}


@app.post("/analyze")
def analyze():
    try:
        owner, repo = parse_repo_url(request.form.get("repo", ""))
    except ValueError as exc:
        return render_template("index.html", username=session.get("username"), error=str(exc)), 400
    # This authenticated request checks that the signed-in user can access the repository.
    github_request(f"/repos/{owner}/{repo}")
    commits = github_request(f"/repos/{owner}/{repo}/commits", {"per_page": 10})
    pulls = github_request(f"/repos/{owner}/{repo}/pulls", {"state": "all", "per_page": 10,
                                                                "sort": "updated", "direction": "desc"})
    push_actors = recent_push_actors(owner, repo)
    history = []
    for item in commits:
        commit_data = item.get("commit", {})
        author_data = commit_data.get("author") or {}
        committer_data = commit_data.get("committer") or {}
        history.append({
            "sha": item["sha"],
            "url": item.get("html_url", "#"),
            "message": commit_data.get("message", "(no commit message)").splitlines()[0],
            "author": (item.get("author") or {}).get("login") or author_data.get("name", "Unknown"),
            "committer": (item.get("committer") or {}).get("login") or committer_data.get("name", "Unknown"),
            "author_date": author_data.get("date", "Unknown date"),
            "push_actor": push_actors.get(item["sha"]),
        })
    reports = []
    for item in commits[:5]:
        detail = github_request(f"/repos/{owner}/{repo}/commits/{item['sha']}")
        reports.append(risk_assessment(owner, repo, detail, push_actors.get(item["sha"])))
    return render_template("results.html", username=session.get("username"), reports=reports,
                           history=history, pulls=pulls, repo=f"{owner}/{repo}")


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
