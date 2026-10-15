"""Context-length probes for llama.cpp-family servers: llama-server's /props and llama-swap's
resident-gated per-model /props.

Split out of ``agent/model_metadata.py``; ``_query_local_context_length_uncached`` there picks the
probe for the detected server type. The integer coercers are late-imported from the facade.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote


def _llamacpp_context(client, server_url: str, model: str) -> Optional[int]:
    """llama.cpp /props: the RUNTIME n_ctx, answered by the router even for a not-yet-loaded model
    (while /v1/models has meta=null), so a lazily-loaded model doesn't fall to a family catch-all."""
    import httpx

    from agent.model_metadata import _positive_int
    for props_path in (f"/props?model={model}", "/props"):
        try:
            resp = client.get(f"{server_url}{props_path}")
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            continue
        n_ctx = _positive_int((resp.json().get("default_generation_settings") or {}).get("n_ctx"))
        if n_ctx is not None:
            return n_ctx
    return None


def _props_reported_n_ctx(payload: Any) -> Optional[int]:
    """The runtime ``n_ctx`` from a llama.cpp ``/props`` payload: ``default_generation_settings.n_ctx`` is the
    context the server actually allocated, authoritative over ``n_ctx_train`` and over /v1/models metadata."""
    from agent.model_metadata import _coerce_reasonable_int

    if not isinstance(payload, dict):
        return None
    gen_settings = payload.get("default_generation_settings")
    if not isinstance(gen_settings, dict):
        return None
    return _coerce_reasonable_int(gen_settings.get("n_ctx"))


def _llamaswap_context(client, server_url: str, model: str) -> Optional[int]:
    """llama-swap /props per model, resident-gated. Any model-scoped route STARTS a non-resident model, and a
    metadata probe must never load a model: consult /running first and query /props only for resident ids.
    A non-resident model yields None; callers keep the cached or default value until a real request starts it."""
    resp = client.get(f"{server_url}/running")
    if resp.status_code != 200:
        return None
    try:
        entries = resp.json().get("running") or []
    except (ValueError, AttributeError):  # not JSON, or not an object
        entries = []
    resident = {str(entry.get("model")) for entry in entries if isinstance(entry, dict) and entry.get("model")}
    if model not in resident:
        return None
    resp = client.get(f"{server_url}/props?model={quote(model, safe='')}")
    if resp.status_code != 200:
        return None
    try:
        payload = resp.json()
    except ValueError:
        return None
    return _props_reported_n_ctx(payload)
