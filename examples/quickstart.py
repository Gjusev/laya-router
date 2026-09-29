"""Phase 1 acceptance criterion in 10 lines: use the proxy with the OpenAI SDK
without changing anything else in your code.

First: pip install openai && laya-router   (serves http://127.0.0.1:8000/v1)
"""

from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="your-upstream-key")

completion = client.chat.completions.create(
    model="ignored-by-proxy",  # laya-router picks the model for you
    messages=[{"role": "user", "content": "Say hi in three words"}],
)
print(completion.model, "->", completion.choices[0].message.content)
