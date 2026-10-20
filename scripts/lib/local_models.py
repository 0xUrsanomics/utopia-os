#!/usr/bin/env python3
# local_models.py: LOAD, RUN, UNLOAD runner for local models so nothing stays resident on a shared GPU.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Shared runner for local models on a single shared GPU (OPTIONAL module).

Every call follows LOAD, RUN, UNLOAD: start the model server on 127.0.0.1, do the batch, stop it.
Nothing stays resident, so other GPU jobs (speech-to-text, a nightly embedding reindex) keep their
VRAM. A file lock serializes callers: scheduled harvesters overlap on the clock, and two models
loading at once is how a box runs out of VRAM.

Backends (configure by env; nothing is assumed installed):
  llama_generate(prompts, max_tokens, ctx)   llama.cpp `llama-server`, started and stopped per batch
      LOCAL_LLAMA_SERVER   path to the llama-server binary
      LOCAL_LLAMA_MODEL    path to the .gguf model
      LOCAL_LLAMA_LIBS     optional LD_LIBRARY_PATH prefix (CUDA libs for a custom build)
  ollama_generate(prompts, num_predict, model, num_ctx)   an already-running Ollama, unloaded after
      LOCAL_OLLAMA_URL     default http://localhost:11434
      LOCAL_OLLAMA_MODEL   default model tag (no default; pass --model or set this)

CLI:
  local_models.py summarize --file <path> [--words 150]      private summary via llama-server
  local_models.py ollama --in <prompts.json> [--max 8] [--model TAG]   one JSON line per prompt
  local_models.py --selftest                                  lock + helpers, no model needed

Callers must treat any exception as "local model unavailable" and fall back (fail-open).
Env: AGENT_RUN_DIR (lock file dir, default ~/.agent-daemon/run).
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

READY_TIMEOUT_S = 180
LOCK = Path(os.environ.get("AGENT_RUN_DIR", str(Path.home() / ".agent-daemon" / "run"))) / "local_models.lock"
LOCK_WAIT_S = 900
OLLAMA = os.environ.get("LOCAL_OLLAMA_URL", "http://localhost:11434")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(url, body, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _wait(proc, url):
    t = time.time()
    while time.time() - t < READY_TIMEOUT_S:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(2)
    raise TimeoutError("server not ready")


@contextmanager
def _gpu_lock(wait_s=None):
    """One local model on the GPU at a time."""
    import fcntl
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    wait_s = LOCK_WAIT_S if wait_s is None else wait_s
    with open(LOCK, "w") as fd:
        t = time.time()
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() - t > wait_s:
                    raise TimeoutError("local model GPU lock busy")
                time.sleep(min(3, max(wait_s, 0.1)))
        yield


@contextmanager
def _server(cmd, cwd, env, ready_url):
    with _gpu_lock():
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            _wait(proc, ready_url)
            yield
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()


def llama_generate(prompts, max_tokens=400, ctx=8192):
    """Chat completions from a llama.cpp server started for this batch.

    No KV-cache quantization flags by default: with -ctk/-ctv q4_0 or q8_0 some llama.cpp forks return
    garbage ('////') for prompts of a few thousand tokens and stay broken for later requests. Short
    test prompts look fine, so test with a long prompt before turning it on."""
    server = os.environ.get("LOCAL_LLAMA_SERVER", "")
    model = os.environ.get("LOCAL_LLAMA_MODEL", "")
    if not (server and model and os.path.exists(server) and os.path.exists(model)):
        raise RuntimeError("set LOCAL_LLAMA_SERVER and LOCAL_LLAMA_MODEL to an existing binary and .gguf")
    port = _free_port()
    env = dict(os.environ)
    if os.environ.get("LOCAL_LLAMA_LIBS"):
        env["LD_LIBRARY_PATH"] = os.environ["LOCAL_LLAMA_LIBS"] + ":" + env.get("LD_LIBRARY_PATH", "")
    cmd = [server, "-m", model, "--host", "127.0.0.1", "--port", str(port),
           "-ngl", "99", "-c", str(ctx), "-fa", "on", "--jinja"]
    out = []
    with _server(cmd, str(Path(server).parent), env, f"http://127.0.0.1:{port}/health"):
        for p in prompts:
            r = _post(f"http://127.0.0.1:{port}/v1/chat/completions", {
                "messages": [{"role": "user", "content": p}], "temperature": 0.2, "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": False}})
            out.append(r["choices"][0]["message"]["content"].strip())
    return out


def ollama_generate(prompts, num_predict=8, model=None, num_ctx=8192):
    """Short answers from an already-running Ollama. think=False, or a thinking model returns empty text.
    num_ctx is set explicitly: some models default to a very large context that spills to CPU (about 2x
    slower). There is no server to start; the model is unloaded with keep_alive=0 after the batch."""
    model = model or os.environ.get("LOCAL_OLLAMA_MODEL")
    if not model:
        raise RuntimeError("pass a model tag or set LOCAL_OLLAMA_MODEL")
    out = []
    with _gpu_lock():
        try:
            for p in prompts:
                r = _post(f"{OLLAMA}/api/generate", {"model": model, "prompt": p, "stream": False, "think": False,
                                                      "keep_alive": "2m", "options": {"temperature": 0, "num_predict": num_predict,
                                                                                      "num_ctx": num_ctx}}, timeout=180)
                out.append(r["response"].strip())
        finally:
            try:
                _post(f"{OLLAMA}/api/generate", {"model": model, "keep_alive": 0}, timeout=30)
            except Exception:
                pass
    return out


def summarize_prompt(text, words=150):
    return (f"Summarise the text below in at most {words} words. Keep names, numbers and dates exactly as written. "
            "Do not add facts that are not in the text. Plain sentences, no em dashes.\n\n---\n" + text[:20000])


def _selftest():
    global LOCK
    import tempfile
    import threading
    ok = True
    with tempfile.TemporaryDirectory() as td:
        saved, LOCK = LOCK, Path(td) / "local_models.lock"
        try:
            held = threading.Event()
            release = threading.Event()

            def holder():
                with _gpu_lock():
                    held.set()
                    release.wait(5)
            th = threading.Thread(target=holder)
            th.start()
            held.wait(5)
            try:
                with _gpu_lock(wait_s=0.5):
                    ok = False  # second holder must not get the lock
            except TimeoutError:
                pass
            release.set()
            th.join()
            with _gpu_lock(wait_s=1):
                pass  # free again
        finally:
            LOCK = saved
    ok = ok and 1024 <= _free_port() <= 65535
    ok = ok and "at most 50 words" in summarize_prompt("x", 50)
    try:
        llama_generate(["hi"]) if not os.environ.get("LOCAL_LLAMA_SERVER") else None
        ok = ok and bool(os.environ.get("LOCAL_LLAMA_SERVER"))
    except RuntimeError:
        pass  # unconfigured backend raises, which callers treat as "unavailable"
    print(f"selftest {'PASS' if ok else 'FAIL'}: lock serializes, helpers ok, unconfigured backend fails open")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summarize")
    s.add_argument("--file", required=True)
    s.add_argument("--words", type=int, default=150)
    g = sub.add_parser("ollama")
    g.add_argument("--in", dest="inp", required=True)
    g.add_argument("--max", type=int, default=8)
    g.add_argument("--model", default=None)
    a = ap.parse_args()
    if a.cmd == "ollama":
        prompts = json.loads(Path(a.inp).read_text())
        for p, r in zip(prompts, ollama_generate(prompts, num_predict=a.max, model=a.model)):
            print(json.dumps({"answer": r, "prompt": p[:80]}, ensure_ascii=False))
        return 0
    print(llama_generate([summarize_prompt(Path(a.file).read_text(errors="replace"), a.words)])[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
