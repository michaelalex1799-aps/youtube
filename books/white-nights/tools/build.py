import json, re, sys
sys.path.insert(0, "/tmp/claude-0/-home-user/bab17d81-f947-51b8-9865-b7876d07cf33/scratchpad")
from reels_data import REELS

SRC = "/tmp/claude-0/-home-user/bab17d81-f947-51b8-9865-b7876d07cf33/scratchpad/wn.txt"
OUT = "/home/user/youtube/books/white-nights/reels.json"
WPM = 165

def norm(s):
    s = re.sub(r"\s+", " ", s).strip()
    # rejoin the four decorative drop capitals split by the page layout
    for a, b in [("I t was a wonderful", "It was a wonderful"), ("“W ell, so", "“Well, so"),
                 ("T o-day was a gloomy", "To-day was a gloomy"), ("M y God, how it has all", "My God, how it has all")]:
        s = s.replace(a, b)
    return s

TEXT = norm(open(SRC, encoding="utf-8").read())

def resolve(t):
    """Map a typed quote (straight quotes) to the exact source span."""
    pat = ""
    for ch in t:
        if ch == "'": pat += "[‘’']"
        elif ch == '"': pat += "[“”\"]"
        elif ch.isspace(): pat += r"\s*" if False else " "
        else: pat += re.escape(ch)
    pat = re.sub(" +", " ", pat)
    ms = [m.group(0) for m in re.finditer(pat, TEXT)]
    return ms

errors = []
def fix(t, where):
    ms = resolve(t)
    if not ms:
        errors.append(f"NOT FOUND [{where}]: {t[:90]}")
        return t
    return ms[0]

words = lambda s: len(re.findall(r"[A-Za-z0-9’']+", s))

def distribute(n, total):
    # spread evenly; remainder seconds go to the later (story) shots, hook shot stays shortest
    base, extra = divmod(total, n)
    secs = [base + (1 if i >= n - extra else 0) for i in range(n)]
    assert all(2 <= s <= 6 for s in secs), (n, total, secs)
    return secs

out = []
for r in REELS:
    p = r["part"]
    script = []
    hv_type, hv = r["hook_vo"]
    if hv_type == "book": hv = fix(hv, f"p{p} hook")
    script.append({"type": hv_type, "text": hv})
    for typ, t in r["script"]:
        if typ == "book": t = fix(t, f"p{p}")
        script.append({"type": typ, "text": t})
    script.append({"type": "narrator", "text": r["cliffhanger"]})
    gold = fix(r["gold_quote"], f"p{p} gold")
    bw = sum(words(s["text"]) for s in script if s["type"] == "book")
    tw = sum(words(s["text"]) for s in script)
    dur = round(tw * 60 / WPM)
    if not (45 <= dur <= 75): errors.append(f"p{p} duration {dur}s ({tw} words)")
    if bw / tw < 0.5: errors.append(f"p{p} verbatim ratio {bw/tw:.2f}")
    if len(r["hook_text"].split()) > 9: errors.append(f"p{p} hook_text too long")
    n = len(r["shots"])
    if not 6 <= n <= 12: errors.append(f"p{p} shots {n}")
    try:
        secs = distribute(n, dur)
    except AssertionError as e:
        errors.append(f"p{p} shot timing {e}"); secs = [0]*n
    shots = []
    for s, sec in zip(r["shots"], secs):
        v, g = [x.strip() for x in s.split("|")]
        shots.append({"sec": sec, "visual": v, "graphic": g})
    out.append({"part": p, "section": r["section"], "lines": r["lines"], "title": r["title"],
                "hook_text": r["hook_text"], "hook_vo": hv, "script": script, "shots": shots,
                "gold_quote": gold, "engagement": r["engagement"], "cliffhanger": r["cliffhanger"],
                "duration_sec": dur, "_stats": (bw, tw)})

for e in errors: print(e)
tot = 0
for o in out:
    bw, tw = o.pop("_stats"); tot += o["duration_sec"]
    print(f'{o["part"]:>2} {o["duration_sec"]:>3}s {tw:>3}w book {bw/tw:.0%}  {o["title"]}')
print("TOTAL", tot, "s =", tot/60, "min")
if not errors or "--force" in sys.argv:
    json.dump({"series": "White Nights", "total_parts": len(out), "reels": out},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("written", OUT)
