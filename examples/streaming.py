"""Streaming through the proxy: same two-line adoption, SSE deltas arrive as
the upstream produces them, and the routing headers are readable via
with_raw_response.

First: pip install laya-router openai
       laya-router   (serves http://127.0.0.1:8000/v1)
"""

from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="your-upstream-key")

raw = client.with_raw_response.chat.completions.create(
    model="ignored-by-proxy",
    stream=True,
    messages=[{"role": "user", "content": "Write a two-sentence bedtime story"}],
)
print("routed to:", raw.headers["x-laya-route"], "via", raw.headers["x-laya-model"])

text = ""
for chunk in raw.parse():
    if chunk.choices and chunk.choices[0].delta.content:
        text += chunk.choices[0].delta.content
print(text)
