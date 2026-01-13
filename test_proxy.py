#!/usr/bin/env python3
"""测试代理设置对 API 的影响"""

from openai import OpenAI
from dotenv import load_dotenv
import os
import time
import httpx

load_dotenv()

from src.utils.config import PAPER_FILTER_PROMPT

title = "FinDeepForecast: A Live Multi-Agent System"
summary = "Deep Research Agents powered by LLMs have shifted the paradigm."
prompt = PAPER_FILTER_PROMPT.format(title=title, summary=summary)

print(f"Prompt 长度: {len(prompt)} 字符")
print(f"HTTP_PROXY: {os.environ.get('http_proxy', 'Not set')}")
print(f"HTTPS_PROXY: {os.environ.get('https_proxy', 'Not set')}")

# 测试1: 默认方式（可能使用代理）
print("\n=== 测试1: 默认方式 ===")
client1 = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    timeout=180.0,
)
start = time.time()
try:
    resp = client1.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    print(f"成功! 耗时: {time.time()-start:.2f}s")
except Exception as e:
    print(f"失败! 耗时: {time.time()-start:.2f}s, 错误: {e}")

# 测试2: 显式禁用代理
print("\n=== 测试2: 禁用代理 ===")
http_client = httpx.Client(proxy=None)
client2 = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    timeout=180.0,
    http_client=http_client,
)
start = time.time()
try:
    resp = client2.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    print(f"成功! 耗时: {time.time()-start:.2f}s")
except Exception as e:
    print(f"失败! 耗时: {time.time()-start:.2f}s, 错误: {e}")
