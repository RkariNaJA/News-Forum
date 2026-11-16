from news.highlights import Corpus, key_sentences, split_sentences, stem

# Background stories: common news words appear everywhere, so sentences made of them must not win.
BACKGROUND = [
    "Government officials said the market fell on Monday as investors watched the economy.",
    "The government said officials would meet investors to discuss the economy and the market.",
    "Officials said the economy grew as the government cut taxes and the market rose.",
    "Investors said the market and the economy face risks, government officials warned.",
] * 5
CORPUS = Corpus(BACKGROUND)

TITLE = "Nvidia shares slide as Jensen Huang weighs comeback"
KEY = "Nvidia shares fell sharply after reports that Jensen Huang is weighing a comeback to the chipmaker."
STORY = [
    "Government officials said on Monday that the market and the economy were being watched by investors.",
    KEY + " Analysts were surprised by the news.",
    "Investors said the government and the market would face risks as the economy slowed this year.",
    "Jensen Huang left Nvidia last month, and Nvidia shares have lost a fifth of their value since then.",
]


def test_topic_sentences_beat_filler():
    picked = key_sentences(TITLE, STORY, CORPUS)
    assert picked and picked[0] == KEY                         # exact text, so the page can find it
    for filler in (STORY[0], STORY[2]):
        assert filler not in picked


def test_sentences_are_exact_substrings_in_reading_order():
    extra = ["Nvidia said Jensen Huang would not comment on reports about his comeback plans this week.",
             "Shares of Nvidia, the chipmaker Jensen Huang founded, slid further in late trading on Tuesday.",
             "Investors said the market would watch the economy and government officials closely next year."]
    long_story = STORY + extra * 3                             # 15+ sentences -> more than one pick
    picked = key_sentences(TITLE, long_story, CORPUS)
    assert 1 < len(picked) <= 3 and len(set(picked)) == len(picked)   # never the same sentence twice
    assert all(any(s in p for p in long_story) for s in picked)
    positions = [next(i for i, p in enumerate(long_story) if s in p) for s in picked]
    assert positions == sorted(positions)                      # reading order


def test_short_and_empty_stories():
    assert key_sentences("", [], CORPUS) == []
    assert key_sentences(TITLE, ["Too short."], CORPUS) == []
    assert len(key_sentences(TITLE, [KEY], CORPUS)) == 1


def test_headline_repeated_as_a_sentence_is_not_picked():
    story = [TITLE + ".", KEY]
    assert key_sentences(TITLE, [TITLE, KEY], CORPUS) == [KEY]
    assert TITLE not in key_sentences(TITLE, story, CORPUS)


def test_split_sentences_handles_abbreviations_and_quotes():
    p = 'Mr. Huang met U.S. officials in Washington. "It went well," he said. Donald J. Trump agreed! Shares rose 4.8%.'
    assert split_sentences(p) == [
        "Mr. Huang met U.S. officials in Washington.",
        '"It went well," he said.',
        "Donald J. Trump agreed!",
        "Shares rose 4.8%.",
    ]


def test_source_name_words_weigh_nothing():
    story = ["Reuters reported that Reuters editors at Reuters spoke to Reuters staff on Reuters matters today.",
             "Acme Corp said Acme Corp profits doubled as Acme Corp sold more widgets to new customers."]
    assert key_sentences("Acme profits double", story, CORPUS, exclude=["Reuters"]) == [story[1]]


def test_stem_groups_simple_forms():
    assert stem("gorillas") == "gorilla" and stem("jojo's") == "jojo"
    assert stem("companies") == "company" and stem("crashes") == "crash"
    assert stem("bus") == "bus" and stem("class") == "class" and stem("analysis") == "analysis"


def test_a_restated_point_is_not_highlighted_twice():
    bullet = "Nvidia shares fell sharply after reports that Jensen Huang may make a comeback to the chipmaker."
    story = [bullet, KEY] + [f"Jensen Huang founded Nvidia, the chipmaker, and ran Nvidia for decade {i}." for i in range(14)]
    picked = key_sentences(TITLE, story, CORPUS)
    assert len(picked) >= 2 and not (bullet in picked and KEY in picked)
