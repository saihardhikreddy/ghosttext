"""Unit tests for the typing logic, with the OS bits faked out.
Run:  .venv\\Scripts\\python -m pytest tests -q   (or just python tests\\test_engine.py)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ghosttext import win32 as w  # noqa: E402
from ghosttext.autocorrect import AutoCorrect  # noqa: E402
from ghosttext.completer import clean_completion  # noqa: E402
from ghosttext.engine import Engine  # noqa: E402

_AC = AutoCorrect()


class FakeOverlay:
    visible = False
    hwnd = None
    on_show = None

    def hide_now(self):
        self.visible = False

    def hide(self):
        self.visible = False

    def show(self, *a):
        pass


class FakeInjector:
    busy = False

    def __init__(self):
        self.sent = []

    def submit(self, text, backspaces):
        self.sent.append((text, backspaces))


class FakeConfig(dict):
    def __init__(self):
        super().__init__(enabled=True, autocomplete=True, autocorrect=True, debounce_ms=0,
                         ignored_words=[], excluded_apps=[], type_delay_ms=12)

    def __setitem__(self, k, v):
        dict.__setitem__(self, k, v)


class FakeModel:
    ready = False


def make_engine():
    e = Engine(FakeConfig(), FakeOverlay(), FakeModel())
    e.autocorrect = _AC
    e.injector = FakeInjector()
    e._check_focus = lambda: None
    e.worker.schedule = lambda *a: None
    return e


class Key:
    def __init__(self, vk):
        self.vkCode, self.scanCode, self.flags, self.dwExtraInfo = vk, 0, 0, 0


def type_into(e, text):
    """Feed characters through the hook logic; mimic the app applying our injections."""
    screen = ""
    for ch in text:
        before = len(e.injector.sent)
        if ch == "\n":
            vk = w.VK_RETURN
        elif ch == " ":
            vk = w.VK_SPACE
        else:
            vk = w.VK_PACKET
        k = Key(vk)
        if vk == w.VK_PACKET:
            k.scanCode = ord(ch)
        swallowed = e._on_key(w.WM_KEYDOWN, k)
        e._on_key(w.WM_KEYUP, k)
        if not swallowed:
            screen += ch
        for text_, bs in e.injector.sent[before:]:
            screen = screen[:len(screen) - bs] + text_
    return screen


def backspace(e, screen):
    before = len(e.injector.sent)
    k = Key(w.VK_BACK)
    if not e._on_key(w.WM_KEYDOWN, k):
        screen = screen[:-1]
    e._on_key(w.WM_KEYUP, k)
    for text_, bs in e.injector.sent[before:]:
        screen = screen[:len(screen) - bs] + text_
    return screen


def test_autocorrect_sentence():
    e = make_engine()
    out = type_into(e, "i think teh quick brwon fox is realy wierd. dont worry ")
    assert out == "I think the quick brown fox is really weird. don't worry ", out
    assert e.buffer == out


def test_leaves_names_urls_and_code_alone():
    e = make_engine()
    out = type_into(e, "see github.com/hardhik and foo_bar or Hardhik ")
    assert out == "see github.com/hardhik and foo_bar or Hardhik ", out


def test_backspace_undoes_fix_and_learns_word():
    e = make_engine()
    screen = type_into(e, "hello teh ")
    assert screen == "hello the "
    screen = backspace(e, screen)
    assert screen == "hello teh ", screen
    assert "teh" in e.autocorrect.ignored
    screen += type_into(e, "teh ")
    assert screen.endswith("teh teh "), screen
    e.autocorrect.ignored.discard("teh")


def test_ghost_accept_with_tab():
    e = make_engine()
    type_into(e, "thanks for your ")
    e.ghost = "help with this"
    k = Key(w.VK_TAB)
    assert e._on_key(w.WM_KEYDOWN, k) is True
    assert e._on_key(w.WM_KEYUP, k) is True  # key-up swallowed too
    assert e.injector.sent[-1] == ("help with this", 0)
    assert e.buffer.endswith("your help with this")
    assert e.ghost is None


def test_typing_through_ghost_keeps_it():
    e = make_engine()
    type_into(e, "see you ")
    e.ghost = "tomorrow"
    type_into(e, "to")
    assert e.ghost == "morrow"
    type_into(e, "x")
    assert e.ghost is None


def test_lowercase_names_left_alone():
    for name in ["priya", "reddy", "kiran", "ravi", "teja", "rahul", "hardhik", "sneha"]:
        assert _AC.correct(name) is None, name


def test_finger_slips_fixed():
    for typo, fix in [("wwter", "water"), ("ooint", "point"), ("thsi", "this"), ("realy", "really"),
                      ("meetign", "meeting"), ("peopel", "people"), ("lazzy", "lazy")]:
        assert _AC.correct(typo) == fix, (typo, _AC.correct(typo))


def test_clean_completion():
    assert clean_completion("I am going to the ", " store to buy milk. Then home") == "store to buy milk."
    assert clean_completion("Thanks for your hel", "p with the project.") == "p with the project."
    assert clean_completion("ok", "\n\nfoo") is None
    assert clean_completion("Let me know if", " you have any questions or concer", 4, truncated=True) == " you have any questions"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
