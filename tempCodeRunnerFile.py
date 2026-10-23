
    if not token:
        abort(401, "Please sign in with GitHub first.")
    response = requests.get(
        f"{GITHUB_API}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept