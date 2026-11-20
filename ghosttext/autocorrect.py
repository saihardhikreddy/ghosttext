"""Conservative typo correction: a hand-made list of common slips plus SymSpell
(edit distance) over an 82k-word English frequency dictionary."""
import os
import re

# Common slips that SymSpell either misses or can't decide on (contractions etc.).
TYPOS = {
    "i": "I", "im": "I'm", "ive": "I've", "ill": None, "id": None,
    "teh": "the", "hte": "the", "adn": "and", "nad": "and", "taht": "that", "thta": "that",
    "waht": "what", "wiht": "with", "whit": None, "becuase": "because", "becasue": "because",
    "dont": "don't", "doesnt": "doesn't", "didnt": "didn't", "isnt": "isn't", "wasnt": "wasn't",
    "arent": "aren't", "werent": "weren't", "couldnt": "couldn't", "wouldnt": "wouldn't",
    "shouldnt": "shouldn't", "havent": "haven't", "hasnt": "hasn't", "hadnt": "hadn't",
    "cant": "can't", "wont": "won't", "youre": "you're", "theyre": "they're", "thats": "that's",
    "whats": "what's", "theres": "there's", "heres": "here's", "wouldve": "would've",
    "couldve": "could've", "shouldve": "should've", "youve": "you've", "weve": "we've",
    "theyve": "they've", "youll": "you'll", "theyll": "they'll", "itll": "it'll",
    "alot": "a lot", "recieve": "receive", "recieved": "received", "definately": "definitely",
    "definatly": "definitely", "seperate": "separate", "occured": "occurred", "untill": "until",
    "wierd": "weird", "tommorow": "tomorrow", "tomorow": "tomorrow", "tommorrow": "tomorrow",
    "thier": "their", "beleive": "believe", "acheive": "achieve", "accomodate": "accommodate",
    "goverment": "government", "enviroment": "environment", "neccessary": "necessary",
    "necesary": "necessary", "occassion": "occasion", "existance": "existence",
    "publically": "publicly", "truely": "truly", "wich": "which", "freind": "friend",
    "begining": "beginning", "calender": "calendar", "collegue": "colleague",
    "adress": "address", "arguement": "argument", "basicly": "basically", "concious": "conscious",
    "embarass": "embarrass", "familar": "familiar", "finaly": "finally", "foriegn": "foreign",
    "gaurd": "guard", "happend": "happened", "immediatly": "immediately", "independant": "independent",
    "knowlege": "knowledge", "liason": "liaison", "maintainance": "maintenance", "mispell": "misspell",
    "noticable": "noticeable", "persue": "pursue", "posession": "possession", "prefered": "preferred",
    "realy": "really", "refered": "referred", "relevent": "relevant", "remeber": "remember",
    "resturant": "restaurant", "sucess": "success", "succesful": "successful", "suprise": "surprise",
    "tounge": "tongue", "wether": "whether", "writting": "writing", "yeild": "yield",
    "helo": "hello", "jsut": "just", "knwo": "know", "konw": "know", "nwo": "now",
    "thanx": None, "pls": None, "plz": None,
}

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def match_case(src, dst):
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


class AutoCorrect:
    def __init__(self, ignored=()):
        from symspellpy import SymSpell, Verbosity
        import symspellpy

        self._verbosity = Verbosity
        self.sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        path = os.path.join(os.path.dirname(symspellpy.__file__), "frequency_dictionary_en_82_765.txt")
        self.sym.load_dictionary(path, term_index=0, count_index=1)
        self.words = self.sym.words
        self.ignored = {w.lower() for w in ignored}

    def ignore(self, word):
        self.ignored.add(word.lower())

    def is_known(self, lower):
        if lower in self.words:
            return True
        if lower.endswith("'s") and lower[:-2] in self.words:
            return True
        if "'" in lower:  # contractions like "we'd" aren't in the frequency list
            return True
        return False

    def correct(self, word, sentence_start=False):
        """Return the replacement for `word`, or None to leave it alone."""
        if not word or not _WORD.fullmatch(word):
            return None
        lower = word.lower()
        if lower in self.ignored:
            return None
        if lower in TYPOS:
            fix = TYPOS[lower]
            if fix is None:
                return None
            if lower == "i":
                return "I" if word == "i" else None
            return match_case(word, fix) if fix != "I'm" and fix != "I've" else fix
        if len(word) < 3:
            return None
        if word.isupper():  # acronyms
            return None
        if any(c.isupper() for c in word[1:]):  # camelCase, McDonald...
            return None
        if word[0].isupper() and not sentence_start:  # probably a name
            return None
        if self.is_known(lower):
            return None

        max_dist = 2 if len(lower) >= 6 else 1
        hits = self.sym.lookup(lower, self._verbosity.CLOSEST, max_edit_distance=max_dist,
                               include_unknown=False)
        if not hits:
            return None
        hits.sort(key=lambda s: (s.distance, -s.count))
        best = hits[0]
        same = [h for h in hits[1:] if h.distance == best.distance]
        # Only fix when one candidate clearly dominates; otherwise it's a guess.
        if same and best.count < 4 * same[0].count:
            return None
        if best.count < 50_000 and best.distance > 1:
            return None
        return match_case(word, best.term)
