"""
GitHub auto-commit — pushes the SQLite .db file after every write operation.

Requires st.secrets["GITHUB_TOKEN"] and st.secrets["GITHUB_REPO"].
If either secret is absent the function returns False silently (dev mode).
"""

from pathlib import Path

import streamlit as st


def push_db_to_github(db_path: Path) -> bool:
    """
    Commits db_path to the configured GitHub repository via the PyGitHub API.
    Returns True on success, False on any failure (non-fatal — shows a warning).
    """
    try:
        token     = st.secrets.get("GITHUB_TOKEN")
        repo_name = st.secrets.get("GITHUB_REPO")
        if not token or not repo_name:
            return False  # secrets absent — skip silently (local dev)

        from github import Github
        g    = Github(token)
        repo = g.get_repo(repo_name)

        with open(db_path, "rb") as f:
            content = f.read()

        remote_path = "dataset/analise_gal.db"
        try:
            existing = repo.get_contents(remote_path)
            repo.update_file(
                remote_path,
                "chore: atualiza banco de dados SQLite [auto]",
                content,
                existing.sha,
            )
        except Exception:
            repo.create_file(
                remote_path,
                "chore: cria banco de dados SQLite [auto]",
                content,
            )
        return True

    except Exception as exc:
        st.warning(f"⚠️ Sincronização com GitHub falhou: {exc}")
        return False
