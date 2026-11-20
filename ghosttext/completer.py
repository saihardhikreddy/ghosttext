"""Runs a private llama.cpp server on 127.0.0.1 and asks it for short continuations."""
import http.client
import json
import logging
import re
import subprocess
import threading
import time

log = logging.getLogger(__name__)
CREATE_NO_WINDOW = 0x08000000


class LocalModel:
    def __init__(self, config):
        self.config = config
        self.port = int(config["server_port"])
        self.proc = None
        self.status = "starting"
        self._lock = threading.Lock()

    # ------------------------------------------------------------ lifecycle
    def start(self):
        threading.Thread(target=self._start, name="model-server", daemon=True).start()

    def _start(self):
        exe, model = self.config.server_exe(), self.config.model_path()
        if not exe or not exe.exists():
            self.status = "llama-server.exe not found (run setup.ps1)"
            return
        if not model or not model.exists():
            self.status = "no model in models\\ (run setup.ps1)"
            return
        if self._healthy():  # already running (e.g. app restarted)
            self.status = "ready"
            return
        args = [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
                "-ngl", str(self.config["gpu_layers"]), "-c", "2048", "-np", "1",
                "--no-webui", "-fa", "auto"]
        log.info("starting %s", " ".join(args))
        try:
            self.proc = subprocess.Popen(args, cwd=str(exe.parent), stdout=subprocess.DEVNULL,
                                         stderr=open(self._log_path(), "w", encoding="utf-8"),
                                         creationflags=CREATE_NO_WINDOW)
        except OSError as e:
            self.status = f"failed to start server: {e}"
            return
        self.status = "loading model"
        for _ in range(240):
            if self.proc.poll() is not None:
                self.status = "server exited (see llama-server.log)"
                return
            if self._healthy():
                self.status = "ready"
                self.warm_up()
                return
            time.sleep(0.5)
        self.status = "server did not become ready"

    def _log_path(self):
        from .config import APP_DIR
        APP_DIR.mkdir(parents=True, exist_ok=True)
        return APP_DIR / "llama-server.log"

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _healthy(self):
        try:
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
            c.request("GET", "/health")
            ok = c.getresponse().status == 200
            c.close()
            return ok
        except OSError:
            return False

    def warm_up(self):
        try:
            self._request("Hello, how are", 4)
        except Exception:
            pass

    @property
    def ready(self):
        return self.status == "ready"

    # ------------------------------------------------------------ inference
    def _request(self, prompt, n_predict, prefix=""):
        req = {
            "prompt": prompt, "n_predict": n_predict, "temperature": 0, "repeat_penalty": 1.1,
            "stop": ["\n", "\r"], "cache_prompt": True, "n_probs": 1,
        }
        if prefix:
            # Force the output to start with what the user already typed (token healing).
            literal = prefix.replace("\\", "\\\\").replace('"', '\\"')
            req["grammar"] = 'root ::= "' + literal + '" [^\\n\\r]*'
        body = json.dumps(req)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        try:
            c.request("POST", "/completion", body, {"Content-Type": "application/json"})
            resp = c.getresponse()
            data = json.loads(resp.read() or b"{}")
        finally:
            c.close()
        return data

    def complete(self, context):
        if not self.ready:
            return None
        with self._lock:
            t = time.perf_counter()
            prompt, prefix = split_for_healing(context)
            data = self._request(prompt, 20, prefix)
            log.debug("completion in %.0f ms", (time.perf_counter() - t) * 1000)
        out = data.get("content", "")
        if not out.startswith(prefix):
            return None
        out, cut = confident_part(data.get("completion_probabilities"), out, len(prefix),
                                  float(self.config["min_token_logprob"]),
                                  float(self.config["min_total_logprob"]))
        return clean_completion(context, out[len(prefix):], int(self.config["max_words"]),
                                truncated=cut or bool(data.get("stopped_limit")))


def confident_part(probs, out, skip_chars, min_token, min_total):
    """Keep the continuation only while the model is sure of it: stop at the first
    token it gave less than e^min_token probability, or once the running total
    drops below e^min_total. Returns (text, was_cut)."""
    if not probs:
        return out, False
    text, seen, total = "", 0, 0.0
    for p in probs:
        tok, lp = p.get("token", ""), p.get("logprob", 0.0)
        if seen < skip_chars:  # the forced prefix the user already typed
            text += tok
            seen += len(tok)
            continue
        total += lp
        if lp < min_token or total < min_total:
            return text, True
        text += tok
    return text if text else out, False


def split_for_healing(context):
    """Models complete badly from a dangling space or half a word, because those
    tokenize unnaturally. Back up to the last whole word and make the model
    regenerate the tail (constrained by a grammar), e.g.
    'thanks for your hel' -> prompt 'thanks for your', must start with ' hel'."""
    if context.endswith(" ") and context.strip():
        return context[:-1], " "
    m = re.search(r" ?[A-Za-z0-9']+\Z", context)
    if m and m.start() > 0:
        return context[:m.start()], m.group(0)
    return context, ""


_DANGLING = {"a", "an", "the", "of", "to", "for", "and", "or", "but", "because", "with", "in",
             "on", "at", "by", "from", "as", "that", "my", "your", "our", "their", "is", "am", "are"}
_SENT_END = re.compile(r"[.!?](?=\s|$)")


def clean_completion(context, out, max_words=6, truncated=False):
    """Trim a raw model continuation into a short, tidy suggestion (or None)."""
    out = out.replace("\r", "").split("\n", 1)[0]
    if not out.strip():
        return None
    if context.endswith((" ", "\t", "\n")):
        out = out.lstrip()
    out = re.sub(r" {2,}", " ", out)
    m = _SENT_END.search(out)
    if m:
        out = out[:m.end()]
        truncated = False
    tokens = re.findall(r"\S+|\s+", out)
    words, kept = 0, []
    for tok in tokens:
        if not tok.isspace():
            words += 1
            if words > max_words:
                truncated = False  # we cut at a word boundary ourselves; all kept words are whole
                break
        kept.append(tok)
    if truncated and sum(1 for k in kept if not k.isspace()) > 1:
        while kept and kept[-1].isspace():
            kept.pop()
        kept.pop()  # last word may be cut off mid-way
    out = "".join(kept).rstrip()
    # A suggestion that stops on "of", "the", "and"... reads like a cliff-hanger; drop those.
    while True:
        m = re.search(r"\s+(\S+)$", out)
        if not m or m.group(1).lower() not in _DANGLING:
            break
        out = out[:m.start()]
    if not out.strip() or not re.search(r"\w", out):
        return None
    # Don't suggest something that just repeats the tail of what was typed.
    if len(out.strip()) > 8 and out.strip() in context[-300:]:
        return None
    return out
