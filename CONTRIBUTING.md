# Contributing to PaperTools

感谢你有兴趣为 PaperTools 做出贡献！

## 开发环境设置

### 1. 克隆仓库

```bash
git clone https://github.com/papertools/papertools.git
cd papertools
```

### 2. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 Windows: venv\Scripts\activate
```

### 3. 安装开发依赖

```bash
pip install -e ".[dev]"
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 API 密钥
```

### 5. 安装 pre-commit hooks

```bash
pre-commit install
```

## 代码规范

### Python 风格

- 使用 [Black](https://black.readthedocs.io/) 进行代码格式化（行宽 100）
- 使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查
- 使用类型注解（Python 3.9+ 语法）
- 遵循 PEP 8 命名规范

### 运行代码检查

```bash
# 格式化代码
ruff format src/

# 检查代码
ruff check src/

# 类型检查
mypy src/
```

### 提交信息格式

使用清晰的提交信息，推荐格式：

```
类型: 简短描述

详细说明（可选）
```

类型包括：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建/工具相关

示例：
```
feat: 添加论文收藏导出功能

- 支持导出为 JSON 和 BibTeX 格式
- 添加批量导出选项
```

## 测试

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_cache_manager.py -v

# 生成覆盖率报告
pytest tests/ --cov=src --cov-report=html
```

### 编写测试

- 测试文件放在 `tests/` 目录
- 文件名以 `test_` 开头
- 测试类以 `Test` 开头
- 测试函数以 `test_` 开头

示例：
```python
class TestMyFeature:
    def test_basic_functionality(self):
        # 测试代码
        assert result == expected
```

## 目录结构

```
PaperTools/
├── src/
│   ├── core/           # 核心功能模块
│   │   ├── crawl_arxiv.py
│   │   ├── paper_filter.py
│   │   ├── generate_summary.py
│   │   ├── generate_unified_index.py
│   │   ├── serve_webpages.py
│   │   └── pipeline.py
│   └── utils/          # 工具模块
│       ├── config.py
│       ├── logger.py
│       ├── cache_manager.py
│       ├── io.py
│       └── exceptions.py
├── tests/              # 测试代码
├── templates/          # Jinja2 模板
├── scripts/            # 维护脚本
└── docs/               # 文档
```

## Pull Request 流程

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### PR 要求

- [ ] 代码通过所有测试
- [ ] 代码通过 linting 检查
- [ ] 添加了必要的测试
- [ ] 更新了相关文档

## 报告 Bug

请在 GitHub Issues 中报告 bug，包含以下信息：

1. **环境信息**: Python 版本、操作系统
2. **重现步骤**: 清晰的步骤说明
3. **预期行为**: 你期望发生什么
4. **实际行为**: 实际发生了什么
5. **日志/错误信息**: 相关的错误输出

## 功能请求

欢迎提出新功能建议！请在 Issues 中描述：

1. 你想解决什么问题
2. 你建议的解决方案
3. 是否愿意自己实现

## 联系方式

- GitHub Issues: 技术问题和 bug
- GitHub Discussions: 一般讨论和问题

---

再次感谢你的贡献！
