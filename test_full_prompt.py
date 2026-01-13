from openai import OpenAI
from src.utils.config import PAPER_FILTER_PROMPT
import time

client = OpenAI(
    api_key='REDACTED_API_KEY',
    base_url='https://chat.sjtu.plus/v1',
)

title = 'FinDeepForecast: A Live Multi-Agent System for Benchmarking Deep Research Agents in Financial Forecasting'
summary = 'Deep Research (DR) Agents powered by advanced Large Language Models (LLMs) have fundamentally shifted the paradigm for completing complex research tasks...'

prompt = PAPER_FILTER_PROMPT.format(title=title, summary=summary)
print(f'Prompt 长度: {len(prompt)} 字符')
print('正在调用 API...')

start = time.time()
completion = client.chat.completions.create(
    model='z-ai/glm-4.7',
    messages=[
        {'role': 'system', 'content': '你是一个专业的学术论文筛选助手。请根据给定的筛选条件，准确判断论文是否符合要求。'},
        {'role': 'user', 'content': prompt},
    ],
    temperature=0.1
)
elapsed = time.time() - start
print(f'耗时: {elapsed:.2f} 秒')
print(f'响应: {completion.choices[0].message.content}')
