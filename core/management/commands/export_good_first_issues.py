"""
Render docs/GOOD_FIRST_ISSUES.md to site/good-first-issues.html.

The HTML page is a generated, committed artifact (same pattern as
api/openapi.json): edit the markdown, re-run this command, commit both.
CI fails when the page is stale. The renderer below is deliberately
tiny — it covers only the markdown this one curated file uses
(headings, bullet lists with continuations, bold, inline code, links)
rather than pulling in a markdown dependency.
"""

import html
import posixpath
import re
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

REPO_BLOB = "https://github.com/pleasefix-1/pleasefix/blob/main/"

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Good first issues — PleaseFix</title>
<meta name="description"
      content="Small, self-contained starter tasks for new PleaseFix contributors.">
<!-- GENERATED FILE — do not edit. Source: docs/GOOD_FIRST_ISSUES.md.
     Regenerate with: python manage.py export_good_first_issues -->
<style>
  :root {{
    --fg: #1a1a1a; --bg: #ffffff; --accent: #0b6e4f; --accent-2: #0b4f6e;
    --muted: #5a5a5a; --card: #f4f6f5; --border: #dde3e0;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --fg: #eaeaea; --bg: #121212; --accent: #4cc38a; --accent-2: #6fb6d8;
      --muted: #a0a0a0; --card: #1d211f; --border: #2e3532;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, sans-serif;
         color: var(--fg); background: var(--bg); line-height: 1.6; }}
  main {{ max-width: 46rem; margin: 0 auto; padding: 0 1.25rem 4rem; }}
  nav.crumbs {{ padding-top: 1rem; font-size: .9rem; }}
  h1 {{ font-size: 1.8rem; margin: 1.5rem 0 .5rem; }}
  h2 {{ margin-top: 2.2rem; font-size: 1.25rem; border-bottom: 2px solid var(--accent);
       display: inline-block; padding-bottom: .1rem; }}
  a {{ color: var(--accent-2); }}
  code {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size: .9em;
         background: var(--card); border: 1px solid var(--border);
         border-radius: .3rem; padding: 0 .25rem; }}
  ul {{ padding-left: 1.3rem; }}
  li {{ margin: .7rem 0; }}
  footer {{ color: var(--muted); font-size: .85rem; margin-top: 3rem;
           border-top: 1px solid var(--border); padding-top: 1rem; }}
</style>
</head>
<body>
<main>
  <nav class="crumbs"><a href="index.html">← PleaseFix</a> ·
    <a href="dev.html">How it works</a> ·
    <a href="contribute.html">Contribute</a></nav>
{body}
  <footer>
    <p>Generated from
    <a href="{blob}docs/GOOD_FIRST_ISSUES.md">docs/GOOD_FIRST_ISSUES.md</a> —
    edit that file and run <code>python manage.py export_good_first_issues</code>.
    CI fails when this page is stale.</p>
  </footer>
</main>
</body>
</html>
"""


def _link_href(href: str) -> str:
    """Relative repo links become GitHub blob URLs (the markdown lives in
    docs/, the page in site/ — repo-relative paths don't resolve there)."""
    if href.startswith(("http://", "https://", "#")):
        return href
    return REPO_BLOB + posixpath.normpath(posixpath.join("docs", href))


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f'<a href="{_link_href(m.group(2))}">{m.group(1)}</a>',
        text,
    )
    return text


def render_markdown(md: str) -> str:
    """The subset of markdown GOOD_FIRST_ISSUES.md uses, nothing more."""
    out: list[str] = []
    paragraph: list[str] = []
    # Each bullet: intro text, optional nested numbered steps, optional
    # trailing text after the steps (e.g. the *Done when:* line).
    items: list[dict[str, Any]] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if items:
            out.append("<ul>")
            for item in items:
                li = _inline(item["text"])
                if item["steps"]:
                    steps = "".join(f"<li>{_inline(s)}</li>" for s in item["steps"])
                    li += f"<ol>{steps}</ol>"
                if item["tail"]:
                    li += f" {_inline(item['tail'])}"
                out.append(f"<li>{li}</li>")
            out.append("</ul>")
            items.clear()

    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush_paragraph()
            flush_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            out.append(f"<h{level}>{_inline(stripped.lstrip('#').strip())}</h{level}>")
        elif stripped.startswith("- "):
            flush_paragraph()
            items.append({"text": stripped[2:], "steps": [], "tail": ""})
        elif items and line.startswith("  ") and re.match(r"\d+\.\s", stripped):
            items[-1]["steps"].append(re.sub(r"^\d+\.\s+", "", stripped))
        elif stripped and line.startswith("    ") and items and items[-1]["steps"]:
            items[-1]["steps"][-1] += " " + stripped  # step continuation line
        elif stripped and line.startswith("  ") and items:
            item = items[-1]  # bullet continuation: before or after the steps
            if item["steps"]:
                item["tail"] = (item["tail"] + " " + stripped).strip()
            else:
                item["text"] += " " + stripped
        elif stripped:
            flush_list()
            paragraph.append(stripped)
        else:
            flush_paragraph()
            flush_list()
    flush_paragraph()
    flush_list()
    return "\n".join(out)


class Command(BaseCommand):
    help = "Regenerate site/good-first-issues.html from docs/GOOD_FIRST_ISSUES.md."

    def handle(self, *args: Any, **options: Any) -> None:
        source = settings.BASE_DIR / "docs" / "GOOD_FIRST_ISSUES.md"
        target = settings.BASE_DIR / "site" / "good-first-issues.html"
        page = PAGE_TEMPLATE.format(body=render_markdown(source.read_text()), blob=REPO_BLOB)
        target.write_text(page)
        self.stdout.write(f"wrote {target.relative_to(settings.BASE_DIR)}")
