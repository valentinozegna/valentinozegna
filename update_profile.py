"""Regenerate dark_mode.svg / light_mode.svg with live GitHub stats.

Runs daily via GitHub Actions. Stdlib only, no dependencies.
"""
import html
import json
import os
import urllib.request
from datetime import date, datetime, timezone

USER = "valentinozegna"
JOINED = date(2014, 3, 2)  # account creation date, drives the commit range
W = 56  # left column width in characters
W2 = 46  # right column width in characters
WIDTH = 880  # fills the README box; GitHub scales it down on narrow screens
RIGHT_X = 490  # WIDTH - 30 margin - W2 chars at ~7.8px

# two tokens by design: the Actions GITHUB_TOKEN yields the contribution-style
# commit count (public + private activity), while a PAT (ACCESS_TOKEN secret)
# sees private repos for the repo list and LOC walk. Either falls back to the other.
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN") or ""
PRIV_TOKEN = os.environ.get("ACCESS_TOKEN") or TOKEN


def gh(url, payload=None, token=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer {token or TOKEN}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read() or "{}")


def graphql(query, variables=None, token=None):
    _, resp = gh("https://api.github.com/graphql", {"query": query, "variables": variables or {}}, token)
    if resp.get("errors"):
        raise RuntimeError(resp["errors"])
    return resp["data"]


def fetch_stats():
    yr_aliases = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y + 1}-01-01T00:00:00Z")'
        " { totalCommitContributions restrictedContributionsCount }"
        for y in range(JOINED.year, datetime.now(timezone.utc).year + 1)
    )
    contrib = graphql(f'query {{ user(login: "{USER}") {{ {yr_aliases} }} }}')["user"]
    commits = sum(
        v["totalCommitContributions"] + v["restrictedContributionsCount"]
        for v in contrib.values()
    )
    u = graphql(f"""
    query {{
      user(login: "{USER}") {{
        id
        repositories(first: 100, ownerAffiliations: OWNER) {{
          totalCount
          nodes {{ name isFork }}
        }}
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {{
          totalCount
        }}
      }}
    }}""", token=PRIV_TOKEN)["user"]
    stats = {
        "repos": u["repositories"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "commits": commits,
    }
    stats.update(loc([n["name"] for n in u["repositories"]["nodes"] if not n["isFork"]], u["id"]))
    return stats


LOC_QUERY = """
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 100, author: {id: $id}, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""


def loc(repo_names, user_id):
    # REST stats/contributors answers 202 forever to the Actions token,
    # so walk own commits on the default branch via GraphQL instead
    add = rem = 0
    for name in repo_names:
        cursor = None
        try:
            while True:
                ref = graphql(LOC_QUERY, {"owner": USER, "name": name, "id": user_id, "cursor": cursor}, token=PRIV_TOKEN)["repository"]["defaultBranchRef"]
                if ref is None:
                    break  # empty repo
                h = ref["target"]["history"]
                add += sum(n["additions"] for n in h["nodes"])
                rem += sum(n["deletions"] for n in h["nodes"])
                if not h["pageInfo"]["hasNextPage"]:
                    break
                cursor = h["pageInfo"]["endCursor"]
        except Exception as e:
            print(f"loc {name}: {e}")
    return {"loc_add": add, "loc_del": rem, "loc": add - rem}


PALETTES = {
    "dark": {"bg": "#0b1020", "border": "#26304a", "h": "#7dd3fc",
             "k": "#c4b5fd", "v": "#e2e8f0", "d": "#3b4560", "g": "#4ade80", "r": "#fb7185"},
    "light": {"bg": "#fbfaff", "border": "#ddd6fe", "h": "#0369a1",
              "k": "#6d28d9", "v": "#1e293b", "d": "#c7cedb", "g": "#15803d", "r": "#be123c"},
}


def kv(key, val, width=W, color="v"):
    dots = "." * max(width - len(key) - len(str(val)) - 3, 1)
    return [(f"{key}: ", "k"), (dots + " ", "d"), (str(val), color)]


def rule(title="", width=W):
    label = f"─ {title} " if title else ""
    return [(label, "h"), ("─" * (width - len(label)), "d")]


def left_lines():
    return [
        [(f"{USER}@github ", "h"), ("─" * (W - len(USER) - 8), "d")],
        kv("OS", "macOS"),
        kv("Host", "Meta"),
        kv("Kernel", "AI x Hardware"),
        kv("IDE", "Claude Code, VS Code"),
        kv("Languages.Programming", "TypeScript, Python, JavaScript"),
        kv("Languages.Real", "Italian, English"),
        kv("Hobbies", "Photography"),
        [],
        [],
        rule("Career.log"),
        kv("Boot", "Berkeley Lab → Fitbit → Apple → Google → Meta"),
        kv("Form.Factors", "wrist → pocket → face"),
    ]


def right_lines(s):
    n = lambda x: f"{x:,}"
    r = lambda k, v, c="v": kv(k, v, W2, c)
    return [
        rule("Contact", W2),
        r("Email", "valentino.zegna@gmail.com"),
        r("LinkedIn", "in/valentinozegna"),
        r("Photography", "valentinozegna.com"),
        [],
        rule("GitHub Stats", W2),
        r("Repos", n(s["repos"])),
        r("Contributed", n(s["contributed"])),
        r("Commits", n(s["commits"])),
        [],
        r("Lines of Code", n(s["loc"])),
        r("Lines.Added", n(s["loc_add"]) + "++", "g"),
        r("Lines.Deleted", n(s["loc_del"]) + "--", "r"),
    ]


def render(mode, stats):
    p = PALETTES[mode]
    cols = [(30, left_lines()), (RIGHT_X, right_lines(stats))]
    h = 42 + max(len(lines) for _, lines in cols) * 21
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{h}" viewBox="0 0 {WIDTH} {h}" '
        'font-family="Consolas, Menlo, monospace" font-size="13px">',
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{h - 1}" rx="10" fill="{p["bg"]}" stroke="{p["border"]}"/>',
    ]
    for x, lines in cols:
        for i, segs in enumerate(lines):
            if not segs:
                continue
            spans = "".join(f'<tspan fill="{p[c]}">{html.escape(t)}</tspan>' for t, c in segs)
            out.append(f'<text x="{x}" y="{35 + i * 21}" xml:space="preserve">{spans}</text>')
    out.append("</svg>")
    return "\n".join(out)


def selfcheck():
    assert len("".join(t for t, _ in kv("OS", "macOS"))) == W
    fake = {k: 10**7 for k in ("repos", "contributed", "commits", "loc", "loc_add", "loc_del")}
    for lines, width in ((left_lines(), W), (right_lines(fake), W2)):
        for segs in lines:
            assert len("".join(t for t, _ in segs)) <= width, segs
    assert len(left_lines()) == len(right_lines(fake))


if __name__ == "__main__":
    selfcheck()
    stats = fetch_stats()
    print("stats:", stats)
    for mode in PALETTES:
        with open(f"{mode}_mode.svg", "w", encoding="utf-8") as f:
            f.write(render(mode, stats))
    print("wrote dark_mode.svg, light_mode.svg")
