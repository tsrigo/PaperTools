#!/usr/bin/env python3
"""测试 API 调用，对比 test_glm.py"""

from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# 打印配置
print("=== 配置信息 ===")
print(f"API_KEY: {os.getenv('OPENAI_API_KEY')[:20]}...")
print(f"BASE_URL: {os.getenv('OPENAI_BASE_URL')}")
print(f"MODEL: {os.getenv('MODEL')}")

# 方式1: 和 test_glm.py 完全一致
print("\n=== 方式1: 硬编码 (test_glm.py 方式) ===")
client1 = OpenAI(
    api_key="REDACTED_API_KEY",
    base_url="https://chat.sjtu.plus/v1",
)
try:
    resp1 = client1.chat.completions.create(
        model="z-ai/glm-4.7",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你是谁？"},
        ],
    )
    print(f"成功: {resp1.choices[0].message.content[:50]}")
except Exception as e:
    print(f"失败: {e}")

# 方式2: 从环境变量读取
print("\n=== 方式2: 环境变量 ===")
client2 = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
try:
    resp2 = client2.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你是谁？"},
        ],
    )
    print(f"成功: {resp2.choices[0].message.content[:50]}")
except Exception as e:
    print(f"失败: {e}")

# 方式3: 加上 temperature
print("\n=== 方式3: 加 temperature=0.1 ===")
try:
    resp3 = client2.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你是谁？"},
        ],
        temperature=0.1,
    )
    print(f"成功: {resp3.choices[0].message.content[:50]}")
except Exception as e:
    print(f"失败: {e}")

# 方式4: 加上 timeout
print("\n=== 方式4: 加 timeout=180 ===")
client4 = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    timeout=180.0,
)
try:
    resp4 = client4.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你是谁？"},
        ],
        temperature=0.1,
    )
    print(f"成功: {resp4.choices[0].message.content[:50]}")
except Exception as e:
    print(f"失败: {e}")

# 方式5: 长文本测试
print("\n=== 方式5: 长文本请求 ===")
long_prompt = """请翻译以下摘要：
Large Language Models (LLMs) have enabled Multi-Agent Systems (MASs) where agents interact through natural language to solve complex tasks or simulate multi-party dialogues. Recent work on LLM-based MASs has mainly focused on architecture design, such as role assignment and workflow orchestration.
"""
try:
    resp5 = client4.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=[
            {"role": "system", "content": "你是翻译助手"},
            {"role": "user", "content": long_prompt},
        ],
        temperature=0.1,
    )
    print(f"成功: {resp5.choices[0].message.content[:100]}")
except Exception as e:
    print(f"失败: {e}")
