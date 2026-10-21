"""HF trending papers: pick unseen ones, download text, mark as covered.

  python papers.py pick --out WORKDIR [--n 3] [--seen PATH]
  python papers.py mark ID [ID ...] [--seen PATH]

Reads are public; no HF token needed.
"""
import argparse, datetime, json, pathlib, sys, urllib.request

BASE = "https://huggingface.co"
# Outside the plugin folder so plugin updates keep the record.
DEFAULT_SEEN = pathlib.Path.home() / ".claude" / "phro-trend" / "seen.json"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "phro-trend"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def load_seen(path):
    p = pathlib.Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def pick(args):
    seen = load_seen(args.seen)
    feed = json.loads(get(f"{BASE}/api/daily_papers?limit=100&sort=trending"))
    fresh = [x["paper"] for x in feed if x["paper"]["id"] not in seen][: args.n]
    if len(fresh) < args.n:
        print(f"warning: only {len(fresh)} unseen papers in trending feed", file=sys.stderr)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = []
    for p in fresh:
        pid = p["id"]
        meta = json.loads(get(f"{BASE}/api/papers/{pid}"))
        md = get(f"{BASE}/papers/{pid}.md")
        md_path = out / f"{pid}.md"
        md_path.write_text(md, encoding="utf-8")
        lines = md.splitlines()
        heads = [f"{i + 1}: {l.strip()[:90]}" for i, l in enumerate(lines) if l.startswith("#")]
        result.append({
            "id": pid,
            "title": meta.get("title"),
            "upvotes": meta.get("upvotes"),
            "published": meta.get("publishedAt", "")[:10],
            "githubRepo": meta.get("githubRepo"),
            "projectPage": meta.get("projectPage"),
            "abstract": meta.get("summary"),
            "md_path": str(md_path),
            "md_lines": len(lines),
            "headings": heads[:60],
        })
    (out / "picked.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in result:
        print(f"{r['id']}  {r['md_lines']} lines  {r['title']}")
    print(f"details: {out / 'picked.json'}")


def mark(args):
    seen = load_seen(args.seen)
    today = datetime.date.today().isoformat()
    for pid in args.ids:
        seen.setdefault(pid, today)
    pathlib.Path(args.seen).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.seen).write_text(json.dumps(seen, indent=1), encoding="utf-8")
    print(f"seen: {len(seen)} papers")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console default is cp949
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("pick"); a.add_argument("--out", required=True); a.add_argument("--n", type=int, default=3)
    b = sub.add_parser("mark"); b.add_argument("ids", nargs="+")
    for s in (a, b):
        s.add_argument("--seen", default=str(DEFAULT_SEEN))
    args = ap.parse_args()
    {"pick": pick, "mark": mark}[args.cmd](args)
