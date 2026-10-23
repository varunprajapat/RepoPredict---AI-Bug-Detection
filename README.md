# RepoPredict (Flask college-project starter)

RepoPredict signs a user in with GitHub OAuth, checks that the user can access a repository, fetches recent commits and pull requests, and shows an explainable demo risk score for the latest five commits.

**Important:** the included score is a small rule-based demonstration. It is not machine learning and cannot guarantee whether a change will cause a bug. The GitHub OAuth scope `repo` can grant access to private repositories authorized by the user. Explain this clearly in a class demo, and never publish your client secret.

## 1. Prerequisites

- Python 3.10 or newer
- A GitHub account
- Internet access

## 2. Create a GitHub OAuth App

On GitHub, open **Settings → Developer settings → OAuth Apps → New OAuth App**. Use:

- Application name: `RepoPredict`
- Homepage URL: `http://127.0.0.1:5000`
- Authorization callback URL: `http://127.0.0.1:5000/callback`

Create the app, copy its **Client ID**, and generate a **Client Secret**. Keep the secret private. The app requests `read:user` and `repo` so it can identify the user and access repositories that user authorizes.

## 3. Configure and run locally (Windows PowerShell)

Open PowerShell in this `RepoPredict` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Edit `.env`: set `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and replace `FLASK_SECRET_KEY` with a long random value. For example, generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. Leave the callback URL as shown for local development. Then start the site:

```powershell
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000), sign in with GitHub, and enter `owner/repository` or a GitHub repository URL. The signed-in user needs permission to access that repository.

## 4. How the fetching works

After OAuth sign-in, the browser holds a signed Flask session containing the GitHub access token. When the user submits a repository, RepoPredict calls GitHub’s API with that token:

- `GET /repos/{owner}/{repo}` checks access.
- `GET /repos/{owner}/{repo}/commits?per_page=10` fetches recent commits.
- `GET /repos/{owner}/{repo}/commits/{sha}` gets each selected commit’s changed files and line counts.
- `GET /repos/{owner}/{repo}/pulls?state=all&per_page=10` fetches recent pull requests.

The code currently scores the latest five commits. For a class demo, use a repository you own or one you are authorized to access.

## 5. Upload the code to GitHub

Create an **empty private repository** on GitHub named `RepoPredict`. From this project folder, run:

```powershell
git init
git add .
git commit -m "Build RepoPredict Flask starter"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/RepoPredict.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username. `.gitignore` excludes `.env`, so your secret should not be uploaded. Before pushing, confirm `.env` is not listed by `git status`.

## 6. Put it online

A simple option is a Python web host that supports Flask and Gunicorn (for example, Render or Railway). Create a new web service from your GitHub repository and configure:

- Build/install command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Environment variables: `FLASK_SECRET_KEY`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`

After the host gives you an HTTPS address, update the GitHub OAuth App’s **Homepage URL** and **Authorization callback URL**. Set the callback to `https://YOUR-HOST/callback`, then set `GITHUB_REDIRECT_URI` to that same address in the hosting dashboard and redeploy. Keep secrets in the host’s environment-variable settings, never in source code. Hosting free-tier availability and dashboard wording can change, so follow the selected provider’s current Flask deployment guide.

## Project structure

```text
RepoPredict/
  app.py                 Flask routes, OAuth, GitHub API, demo risk scoring
  requirements.txt       Python dependencies
  .env.example           Environment variable template
  templates/             Jinja pages (login, home, results)
```

## Current limitations / ideas to extend

- The risk method uses file names and change size; it does not inspect code semantics.
- It does not yet train on bug-fix history or test whether a commit actually fails.
- GitHub API rate limits apply. Large repositories may need pagination and caching.
- For a stronger model, collect labeled historical commits (bug-inducing vs. non-bug-inducing), create features, train and evaluate a model, and show the evidence behind each score.
