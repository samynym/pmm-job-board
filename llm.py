"""Provider layer: structured extraction + web research on OpenAI or Anthropic.

Provider selection (override with LLM_PROVIDER=openai|anthropic):
  - OPENAI_API_KEY set -> OpenAI (Responses API)
  - else ANTHROPIC_API_KEY set -> Anthropic (Messages API)

Both providers enforce the JSON schema server-side (OpenAI strict structured
outputs / Anthropic output_config.format), so callers just json-parse the
returned text. Raw urllib like the rest of this pipeline — no SDKs.
"""

import json, os, time
import urllib.error, urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"

MODELS = {
    'openai': {'small': os.environ.get('OPENAI_EXTRACT_MODEL', 'gpt-5-mini'),
               'judge': os.environ.get('OPENAI_JUDGE_MODEL', 'gpt-5'),
               'research': os.environ.get('OPENAI_RESEARCH_MODEL', 'gpt-5')},
    'anthropic': {'small': 'claude-haiku-4-5',
                  'judge': 'claude-sonnet-5',
                  'research': os.environ.get('RESEARCH_MODEL', 'claude-sonnet-5')},
}


def provider():
    p = os.environ.get('LLM_PROVIDER')
    if p in ('openai', 'anthropic'):
        return p
    if os.environ.get('OPENAI_API_KEY'):
        return 'openai'
    if os.environ.get('ANTHROPIC_API_KEY'):
        return 'anthropic'
    return None


def _post(url, body, headers, timeout=600, retries=3):
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={**headers, "content-type": "application/json",
                                              "user-agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503, 529):
                last = e
                wait = int(e.headers.get('retry-after') or 0) or (15 * (attempt + 1))
                time.sleep(wait)
                continue
            raise
        except (TimeoutError, OSError) as e:
            last = e
            time.sleep(10)
    raise last


# ---------------------------------------------------------------------------
# OpenAI (Responses API)
# ---------------------------------------------------------------------------

def _openai_call(model, system, user, schema, web_search=False, effort=None):
    body = {
        "model": model,
        "instructions": system,
        "input": user,
        "text": {"format": {"type": "json_schema", "name": "result",
                            "schema": schema, "strict": True}},
    }
    if effort:
        body["reasoning"] = {"effort": effort}
    if web_search:
        body["tools"] = [{"type": "web_search"}]
    resp = _post("https://api.openai.com/v1/responses", body,
                 {"authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    if resp.get('status') == 'incomplete':
        reason = (resp.get('incomplete_details') or {}).get('reason')
        raise RuntimeError(f"incomplete response: {reason}")
    for item in resp.get('output', []):
        if item.get('type') == 'message':
            for c in item.get('content', []):
                if c.get('type') == 'output_text':
                    return json.loads(c['text'])
    raise RuntimeError(f"no output_text in response (status={resp.get('status')})")


# ---------------------------------------------------------------------------
# Anthropic (Messages API)
# ---------------------------------------------------------------------------

def _anthropic_call(model, system, user, schema, web_search=False, effort=None,
                    max_continuations=6):
    body = {
        "model": model,
        "max_tokens": 16000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    if effort and model != 'claude-haiku-4-5':
        body["output_config"]["effort"] = effort
    if web_search:
        body["tools"] = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": 4},
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3,
             "max_content_tokens": 12000},
        ]
    headers = {"x-api-key": os.environ['ANTHROPIC_API_KEY'],
               "anthropic-version": "2023-06-01"}
    resp = _post("https://api.anthropic.com/v1/messages", body, headers)
    for _ in range(max_continuations):
        if resp.get('stop_reason') != 'pause_turn':
            break
        body["messages"] = [{"role": "user", "content": user},
                            {"role": "assistant", "content": resp['content']}]
        resp = _post("https://api.anthropic.com/v1/messages", body, headers)
    if resp.get('stop_reason') == 'refusal':
        raise RuntimeError('refusal')
    for b in resp.get('content', []):
        if b.get('type') == 'text' and b.get('text', '').strip().startswith('{'):
            return json.loads(b['text'])
    raise RuntimeError(f"no JSON block (stop_reason={resp.get('stop_reason')})")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_json(system, user, schema, tier='small', effort=None):
    p = provider()
    if p == 'openai':
        return _openai_call(MODELS['openai'][tier], system, user, schema,
                            effort=effort or ('low' if tier == 'small' else 'medium'))
    if p == 'anthropic':
        return _anthropic_call(MODELS['anthropic'][tier], system, user, schema)
    raise RuntimeError('no LLM API key configured')


def research_json(system, user, schema, effort='medium', tier='research'):
    p = provider()
    if p == 'openai':
        return _openai_call(MODELS['openai'][tier], system, user, schema,
                            web_search=True, effort=effort)
    if p == 'anthropic':
        return _anthropic_call(MODELS['anthropic'][tier], system, user, schema,
                               web_search=True, effort=effort)
    raise RuntimeError('no LLM API key configured')


def available():
    return provider() is not None
