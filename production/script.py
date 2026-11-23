"""Shot lists and voice-over scripts for the White Nights Episode 1 samples.

Each shot:
  scene    canal | street | pink | room | desk
  opts     scene options (palette, walker, foreground railing, ...)
  vo       voice-over text (book text is Constance Garnett's 1918 translation;
           hook/break/outro lines are the channel's own writing)
  cap      line | gold | hand | words | none   (caption style)
  cam      (cx0, cy0, size0, cx1, cy1, size1) slow camera move, size 1.25 = whole painting
  roll     A-roll / B-roll label for the breakdown cut
  designs  which of the 6 visual designs the shot demonstrates
"""

DESIGNS = {
    1: "Design 1 · One consistent look (blue + gold, the Dreamer)",
    2: "Design 2 · Living painting (slow camera, moving water, fog)",
    "3p": "Design 3 · Emotion code: present = cold blue",
    "3t": "Design 3 · Emotion code: thought = handwriting",
    "3m": "Design 3 · Emotion code: memory = warm amber",
    "3d": "Design 3 · Emotion code: daydream = glowing light",
    4: "Design 4 · Big captions, key quotes in gold",
    5: "Design 5 · Structure aids (title card, Night 1 of 4, next ep)",
    6: "Design 6 · Scene change / storytelling break",
}

NARR = "B-ROLL  ·  under narration (voice = A-roll)"

LONG = [
    dict(scene="canal", opts=dict(pal="present"), cap="line", ui=False, fade_in=1.2, min=7,
         vo="Eight years in one of the biggest cities in the world… and not a single friend.",
         cam=(0.30, 0.42, 1.15, 0.55, 0.50, 1.00), roll=NARR, designs=[2, 1, 4]),
    dict(scene="street", opts=dict(walker=(0.10, 0.03), lightup=False), cap="line", ui=False, min=6,
         vo="Except the houses. He talked to the houses… and one of them talked back.",
         cam=(0.30, 0.55, 1.10, 0.55, 0.55, 0.98), roll=NARR, designs=[2, 6]),
    dict(scene="canal", opts=dict(pal="present", seed=9), overlay="title", cap="none", ui=False, sting=True, min=7,
         subtitle="Episode 1 · The Man Who Talked to Houses",
         vo="White Nights. A sentimental story, from the diary of a dreamer.",
         cam=(0.50, 0.40, 1.20, 0.50, 0.44, 1.10), roll="TITLE CARD", designs=[5, 1]),
    dict(scene="canal", opts=dict(pal="present", fg=True, walker=(0.05, 0.022), fog=0.18), cap="gold",
         vo="It was a wonderful night, such a night as is only possible when we are young, dear reader.",
         cam=(0.35, 0.60, 1.05, 0.50, 0.60, 0.95), roll=NARR, designs=[4, 2, 1]),
    dict(scene="canal", opts=dict(pal="present", seed=4), cap="line",
         vo="The sky was so starry, so bright that, looking at it, one could not help asking oneself whether "
            "ill-humoured and capricious people could live under such a sky.",
         cam=(0.50, 0.55, 1.00, 0.62, 0.28, 0.85), roll=NARR, designs=[2, "3p"]),
    dict(scene="room", cap="hand",
         vo="It suddenly seemed to me that I was lonely, that every one was forsaking me and going away from me.",
         cam=(0.50, 0.50, 1.12, 0.52, 0.48, 1.00), roll=NARR, designs=["3t"]),
    dict(scene="street", opts=dict(walker=(0.0, 0.045), lightup=True), cap="line",
         vo="I know the houses too. As I walk along they seem to run forward in the streets to look out at me "
            "from every window, and almost to say: “Good-morning! How do you do?”",
         cam=(0.25, 0.55, 1.00, 0.62, 0.52, 0.95), roll=NARR, designs=[2, "3p"]),
    dict(scene="pink", opts=dict(), cap="line", paint_frac=(0.62, 0.82), punch_frac=[0.64],
         vo="But I shall never forget an incident with a very pretty little house of a light pink colour. "
            "Suddenly last week I heard a plaintive, “They are painting me yellow!” The villains! The barbarians!",
         cam=(0.50, 0.58, 1.15, 0.50, 0.50, 0.95), roll=NARR, designs=["3m"]),
    dict(scene="desk", cap="line", lower=("STORYTELLING BREAK", "Why doesn't he have a name?"),
         vo="Notice something? We never learn his name. Dostoevsky leaves it blank on purpose. "
            "He could be anyone… even you.",
         cam=(0.50, 0.50, 1.20, 0.50, 0.56, 1.00), roll="A-ROLL  ·  host on camera (desk set placeholder)", designs=[6]),
    dict(scene="canal", opts=dict(pal="dream", particles=True, fog=0.1), cap="line",
         vo="I am a dreamer; I have so little real life that I look upon such moments as this now, as so rare, "
            "that I cannot help going over such moments again in my dreams.",
         cam=(0.40, 0.50, 0.95, 0.55, 0.45, 1.15), roll=NARR, designs=["3d"]),
    dict(scene="canal", opts=dict(pal="present", fg=True, woman=True, walker=(0.04, 0.012), fog=0.3), cap="line",
         vo="Leaning on the canal railing stood a woman with her elbows on the rail. "
            "I heard a muffled sob. Yes! I was not mistaken, the girl was crying.",
         cam=(0.45, 0.62, 1.00, 0.58, 0.64, 0.85), roll=NARR, designs=[2, 1]),
    dict(scene="canal", opts=dict(pal="present", fg=True, woman=True, fog=0.3), overlay="endcard", cap="none",
         fade_out=1.5, min=9,
         question="Would you have gone back to that bridge?", next="Ep. 2 · “I Am a Dreamer”",
         vo="Tomorrow night, she asks for his story. Would you have gone back to that bridge? Tell me in the comments.",
         cam=(0.58, 0.60, 0.95, 0.58, 0.58, 0.90), roll="END SCREEN", designs=[5]),
]

SHORT = [
    dict(scene="street", opts=dict(walker=(0.30, 0.02), lightup=False), cap="words", ui=True, sting=True, min=4.5,
         hook="POV: you're so lonely you make friends with buildings",
         vo="Eight years in Petersburg… and not a single friend.",
         cam=(0.50, 0.55, 1.00, 0.50, 0.52, 0.85), punch=[0.0], roll=NARR, designs=[4, 1]),
    dict(scene="street", opts=dict(walker=(0.0, 0.08), lightup=True), cap="words",
         vo="I know the houses too. As I walk along they seem to run forward to look out at me from every window.",
         cam=(0.25, 0.50, 1.00, 0.72, 0.48, 0.90), roll=NARR, designs=[2, "3p"]),
    dict(scene="pink", opts=dict(), cap="words",
         vo="But I shall never forget a very pretty little house of a light pink colour.",
         cam=(0.50, 0.62, 1.10, 0.50, 0.52, 0.92), roll=NARR, designs=["3m"]),
    dict(scene="pink", opts=dict(v=2), cap="words", paint_frac=(0.40, 0.95), punch_frac=[0.45],
         gold_words=["yellow"],
         vo="Suddenly last week I heard a plaintive… “They are painting me yellow!”",
         cam=(0.50, 0.55, 0.95, 0.50, 0.50, 0.85), roll=NARR, designs=["3m", 4]),
    dict(scene="pink", opts=dict(paint=(-2, -1)), cap="words", cut=True, punch_frac=[0.0, 0.55], min=2.5,
         vo="The villains! The barbarians!",
         cam=(0.50, 0.48, 0.80, 0.50, 0.48, 0.80), roll=NARR, designs=[6]),
    dict(scene="canal", opts=dict(pal="present", fg=True, walker=(0.15, 0.02)), cap="words", stamp=(0.2, "Dostoevsky, 1848"),
         vo="He wrote this in 1848, about a man who talked to houses… because nobody talked to him.",
         cam=(0.45, 0.62, 1.00, 0.55, 0.55, 0.88), roll=NARR, designs=[2, 4]),
    dict(scene="canal", opts=dict(pal="present", fg=True, woman=True, fog=0.3), overlay="endcard", cap="none", fade_out=1.0, min=5,
         question="Would you talk to the houses?", next_label="WATCH THE FULL STORY",
         next="White Nights · Episode 1 on our channel", button="FOLLOW",
         vo="The full story is on the channel. Would you talk to the houses?",
         cam=(0.55, 0.60, 0.95, 0.55, 0.58, 0.90), roll="END SCREEN", designs=[5]),
]

SCRIPTS = {"long": LONG, "short": SHORT}
