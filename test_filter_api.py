#!/usr/bin/env python3
"""测试筛选 API 调用"""

from openai import OpenAI
from dotenv import load_dotenv
import os
import time

load_dotenv()

# 从 config 导入 prompt
from src.utils.config import PAPER_FILTER_PROMPT

# 模拟一篇论文
title = "FinDeepForecast: A Live Multi-Agent System for Benchmarking Deep Research Agents"
summary = """Parallel test-time scaling"""

prompt = PAPER_FILTER_PROMPT.format(title=title, summary=summary)
print(f"Prompt 长度: {len(prompt)} 字符")

client = OpenAI(
    api_key="REDACTED_API_KEY",
    base_url="https://chat.sjtu.plus/v1",
    timeout=180.0,
)

messages = [
    {"role": "system", "content": "你是一个专业的学术论文筛选助手。"},
    {"role": "user", "content": prompt}
]

print("\n开始调用 API...")
start = time.time()

try:
    response = client.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=messages,
        temperature=0.1,
    )
    elapsed = time.time() - start
    print(f"成功! 耗时: {elapsed:.2f}s")
    print(f"响应: {response.choices[0].message.content[:200]}...")
except Exception as e:
    elapsed = time.time() - start
    print(f"失败! 耗时: {elapsed:.2f}s")
    print(f"错误: {e}")
