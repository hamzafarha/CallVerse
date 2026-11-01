"""Local Hugging Face models for the agents, run with ``transformers``.

Each agent role (client, advisor, judge) maps to a model repository on the
Hugging Face Hub. ``callverse llm-pull`` downloads the weights once and pins the
commit of each repository in ``artifacts/traces/llm_models.lock.json``; after that
models load from the local cache only, so no request ever waits on a download.

On a CUDA GPU the weights are 4-bit NF4 (bitsandbytes) with bfloat16 compute: the
3B advisor and the 1.6B judge fit together in a 4 GB laptop GPU. (float16 overflows
in these bf16-trained models and only outputs "!!!"; on a Turing GPU PyTorch
emulates bfloat16 at the same speed and memory.) Roles that point
to the same repository share one loaded model. One generation runs at a time.
"""

import json
import re
import threading
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

TOOL_BLOCK = re.compile(r"<\|?tool_call\|?>\s*(.*?)\s*(?:</tool_call>|$)", re.S)
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)
TOOL_MARKERS = ("<tool_call", "<|tool_call")


# --------------------------------------------------------------------- parsing
def _json_values(text: str) -> list[Any]:
    """Every JSON object or list found in ``text``, in order."""
    decoder = json.JSONDecoder()
    values, index = [], 0
    while index < len(text):
        starts = [i for i in (text.find("{", index), text.find("[", index)) if i >= 0]
        if not starts:
            break
        start = min(starts)
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        values.append(value)
        index = end
    return values


def _as_call(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    function = value.get("function") if isinstance(value.get("function"), dict) else value
    name = function.get("name")
    arguments = function.get("arguments", function.get("parameters", {}))
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    if not isinstance(name, str) or not name:
        return None
    return {"name": name, "arguments": arguments if isinstance(arguments, dict) else {}}


def parse_tool_calls(text: str, tool_names: set[str] | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Split model output into (visible text, tool calls).

    Understands ``<tool_call>{json}</tool_call>`` (SmolLM3, Granite, Qwen),
    ``<|tool_call|>[{json}]`` (Granite 3) and a bare ``{"name": ..., "arguments": ...}``.
    """
    text = THINK_BLOCK.sub("", text)
    calls: list[dict[str, Any]] = []
    for block in TOOL_BLOCK.findall(text):
        for value in _json_values(block):
            for item in value if isinstance(value, list) else [value]:
                call = _as_call(item)
                if call:
                    calls.append(call)
    visible = TOOL_BLOCK.sub("", text).strip()
    known = (lambda c: c["name"] in tool_names) if tool_names is not None else (lambda c: True)
    calls = [c for c in calls if known(c)]
    if not calls and visible.startswith(("{", "[")) and '"name"' in visible:
        values = _json_values(visible)
        found = [
            c for v in values for c in map(_as_call, v if isinstance(v, list) else [v]) if c and known(c)
        ]
        if found:
            calls, visible = found, ""
    return visible, calls


def strip_thinking(text: str) -> str:
    """Model output without ``<think>`` blocks."""
    return THINK_BLOCK.sub("", text).strip()


def json_complete(text: str) -> bool:
    """True once the first JSON object in ``text`` is closed (strings respected)."""
    depth, in_string, escaped, started = 0, False, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
            started = True
        elif char == "}":
            depth -= 1
            if started and depth == 0:
                return True
    return False


class StreamGate:
    """Forwards streamed text to ``sink`` but hides tool-call markup.

    The last few characters are held back until it is clear they do not start a
    ``<tool_call>`` block; once a tool call starts, nothing more is forwarded.
    """

    HOLD = 12

    def __init__(self, sink: Callable[[str], None]) -> None:
        self.sink = sink
        self.pending = ""
        self.closed = False
        self.started = False

    def __call__(self, piece: str) -> None:
        if self.closed or not piece:
            return
        self.pending += piece
        if not self.started:
            head = self.pending.lstrip()
            if not head:
                return
            if head.startswith(("{", "[")):
                self.closed = True  # bare JSON tool call
                return
            self.started = True
            self.pending = head
        marker = min((i for i in (self.pending.find(m) for m in TOOL_MARKERS) if i >= 0), default=-1)
        if marker >= 0:
            self._emit(self.pending[:marker])
            self.closed = True
            return
        if len(self.pending) > self.HOLD:
            self._emit(self.pending[: -self.HOLD])
            self.pending = self.pending[-self.HOLD :]

    def finish(self) -> None:
        if not self.closed:
            self._emit(self.pending)
        self.pending = ""

    def _emit(self, text: str) -> None:
        if text:
            self.sink(text)


def normalize_messages(messages: list[dict[str, Any]], native_tools: bool = True) -> list[dict[str, Any]]:
    """Agent messages -> chat-template messages.

    All system messages are merged into the first one (small models' templates
    accept a single system turn). Tool calls and tool results use the template's
    native format when it has one, otherwise ``<tool_call>`` / ``<tool_response>`` text.
    """
    system = [str(m.get("content", "")) for m in messages if m["role"] == "system"]
    out: list[dict[str, Any]] = [{"role": "system", "content": "\n\n".join(system)}] if system else []
    for message in messages:
        role = message["role"]
        if role == "system":
            continue
        if role == "assistant" and message.get("tool_calls"):
            calls = [
                {
                    "name": c["function"]["name"],
                    "arguments": c["function"].get("arguments") or {},
                }
                for c in message["tool_calls"]
            ]
            if native_tools:
                out.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": [{"type": "function", "function": c} for c in calls],
                    }
                )
            else:
                markup = "".join(f"<tool_call>\n{json.dumps(c)}\n</tool_call>" for c in calls)
                out.append({"role": "assistant", "content": (message.get("content") or "") + markup})
        elif role == "tool":
            if native_tools:
                out.append(
                    {"role": "tool", "name": message.get("tool_name"), "content": str(message["content"])}
                )
            else:
                out.append(
                    {"role": "user", "content": f"<tool_response>\n{message['content']}\n</tool_response>"}
                )
        else:
            out.append({"role": role, "content": str(message.get("content", ""))})
    return out


def tools_prompt(tools: list[dict[str, Any]]) -> str:
    """Tool instructions for a chat template without native tool support."""
    listing = "\n".join(json.dumps(t["function"]) for t in tools)
    return (
        "You can call these tools:\n<tools>\n"
        f"{listing}\n</tools>\n"
        "To call one, answer only with "
        '<tool_call>{"name": <tool name>, "arguments": {...}}</tool_call>.'
    )


# ---------------------------------------------------------------------- models
@dataclass
class ModelOptions:
    """Per-repository options from the ``catalog`` of ``configs/agents.yaml``."""

    chat_template_kwargs: dict[str, Any] = field(default_factory=dict)
    tools_kwarg: str = "tools"


class LocalModel:
    """One tokenizer + causal LM, loaded once."""

    def __init__(self, repo: str, revision: str | None, device: str, options: ModelOptions) -> None:
        import torch
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from transformers.utils import logging

        logging.set_verbosity_error()  # no per-call generation-config warnings in the API log
        logging.disable_progress_bar()
        self.repo, self.revision, self.options = repo, revision, options
        kwargs: dict[str, Any] = {"revision": revision, "local_files_only": True}
        self.tokenizer = AutoTokenizer.from_pretrained(repo, **kwargs)
        config = AutoConfig.from_pretrained(repo, **kwargs)
        prequantized = getattr(config, "quantization_config", None) is not None
        self.device = "cuda" if device in ("auto", "cuda") and torch.cuda.is_available() else "cpu"
        if self.device == "cuda":
            quantization = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
            with warnings.catch_warnings():
                # pre-quantized repos keep their saved config; transformers warns about it
                warnings.filterwarnings("ignore", message=".*quantization_config.*")
                self.model = AutoModelForCausalLM.from_pretrained(
                    repo, dtype=torch.bfloat16, device_map={"": 0}, quantization_config=quantization, **kwargs
                )
            self.quantization = "4-bit NF4 (bitsandbytes), bfloat16 compute"
        else:
            if prequantized:
                raise RuntimeError(f"{repo} has 4-bit bitsandbytes weights, which need a CUDA GPU.")
            self.model = AutoModelForCausalLM.from_pretrained(repo, dtype=torch.float32, **kwargs)
            self.quantization = "float32 (CPU)"
        self.model.eval()
        template = self.tokenizer.chat_template or ""
        self.native_tools = "tool_calls" in template and "tool" in template
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.footprint_mb = round(self.model.get_memory_footprint() / 2**20)

    def render(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> str:
        """Prompt text from the model's own chat template."""
        kwargs = dict(self.options.chat_template_kwargs)
        native = self.native_tools or self.options.tools_kwarg != "tools"
        chat = normalize_messages(messages, native_tools=self.native_tools)
        if tools and native:
            kwargs[self.options.tools_kwarg] = tools
        elif tools:
            chat[0]["content"] = f"{chat[0]['content']}\n\n{tools_prompt(tools)}"
        return self.tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True, **kwargs)

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        json_mode: bool,
        temperature: float,
        seed: int,
        max_new_tokens: int,
        on_token: Callable[[str], None] | None = None,
    ) -> tuple[str, int, int]:
        """(text, prompt tokens, completion tokens) for one chat turn."""
        import torch
        from transformers import StoppingCriteriaList, TextIteratorStreamer, set_seed

        prompt = self.render(messages, tools)
        # No prefill for JSON: a lone "{" tokenizes unlike the model's own '{"' token and
        # makes small models stop at once. Generation stops when the object is closed.
        prefix = ""
        inputs = self.tokenizer(prompt + prefix, return_tensors="pt", add_special_tokens=False).to(
            self.device
        )
        start = int(inputs["input_ids"].shape[1])
        kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "pad_token_id": self.tokenizer.pad_token_id,
            "do_sample": temperature > 0,
        }
        if temperature > 0:
            kwargs.update(temperature=temperature, top_p=0.9)
        else:
            kwargs.update(temperature=None, top_p=None, top_k=None)
        if json_mode:
            kwargs["stopping_criteria"] = StoppingCriteriaList([JsonStop(self.tokenizer, start, prefix)])
        set_seed(seed)
        if on_token is None:
            with torch.inference_mode():
                output = self.model.generate(**inputs, **kwargs)
            new = output[0, start:]
            text = self.tokenizer.decode(new, skip_special_tokens=True)
            return prefix + text, start, int(new.shape[0])

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=300
        )
        holder: dict[str, Any] = {}

        def work() -> None:
            try:
                with torch.inference_mode():
                    holder["output"] = self.model.generate(**inputs, **kwargs, streamer=streamer)
            except Exception as error:  # re-raised in the caller's thread
                holder["error"] = error
                streamer.end()

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        pieces = []
        for piece in streamer:
            pieces.append(piece)
            on_token(piece)
        thread.join()
        if "error" in holder:
            raise holder["error"]
        completion = int(holder["output"].shape[1]) - start
        return prefix + "".join(pieces), start, completion


class JsonStop:
    """Stopping criterion: stop as soon as the JSON answer is complete."""

    def __init__(self, tokenizer: Any, start: int, prefix: str) -> None:
        self.tokenizer, self.start, self.prefix = tokenizer, start, prefix

    def __call__(self, input_ids: Any, scores: Any, **kwargs: Any) -> Any:
        import torch

        text = self.prefix + self.tokenizer.decode(input_ids[0, self.start :], skip_special_tokens=True)
        done = json_complete(text)
        return torch.full((input_ids.shape[0],), done, dtype=torch.bool, device=input_ids.device)


class ModelPool:
    """Loaded models, keyed by repository. Thread-safe; one generation at a time."""

    def __init__(self) -> None:
        self._models: dict[str, LocalModel] = {}
        self._load_lock = threading.Lock()
        self.generate_lock = threading.Lock()

    def get(self, repo: str, revision: str | None, device: str, options: ModelOptions) -> LocalModel:
        with self._load_lock:
            if repo not in self._models:
                try:
                    self._models[repo] = LocalModel(repo, revision, device, options)
                except Exception as error:
                    if "out of memory" not in str(error).lower() or not self._models:
                        raise
                    self.unload()  # free the GPU for the model that is needed now
                    self._models[repo] = LocalModel(repo, revision, device, options)
            return self._models[repo]

    def loaded(self) -> dict[str, LocalModel]:
        return dict(self._models)

    def unload(self) -> None:
        import gc

        self._models.clear()
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


def gpu_info() -> dict[str, Any] | None:
    """Name and memory of the CUDA GPU, or None."""
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    free, total = torch.cuda.mem_get_info()
    return {
        "name": torch.cuda.get_device_name(0),
        "total_mb": round(total / 2**20),
        "used_mb": round((total - free) / 2**20),
        "torch_cuda": torch.version.cuda,
    }
