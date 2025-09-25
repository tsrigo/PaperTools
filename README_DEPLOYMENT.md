# 🚀 MyArxiv网站部署指南

本指南将帮助您将PaperTools生成的学术论文网站部署到GitHub Pages。

## 📋 部署前准备

1. **确保已生成网站文件**
```bash
# 运行流水线生成网站
python papertools.py run --mode quick

# 检查生成的文件
ls -la webpages/
```

2. **准备GitHub仓库**
   - 在GitHub上创建新的公开仓库（如：`myarxiv-website`）
   - 不要初始化README、.gitignore或LICENSE

## 🎯 部署方案

### 方案一：手动部署（推荐新手）

```bash
# 1. 初始化Git仓库
cd /home/kai/projects/PaperTools
git init

# 2. 添加文件
git add .
git commit -m "Initial commit: MyArxiv website"

# 3. 连接到GitHub仓库（替换为您的仓库地址）
git branch -M main
git remote add origin https://github.com/您的用户名/您的仓库名.git
git push -u origin main

# 4. 在GitHub仓库设置中启用Pages
# Settings → Pages → Source: Deploy from a branch
# Branch: main, Folder: /webpages
```

### 方案二：GitHub Actions自动部署（推荐）

我已经为您创建了自动部署配置文件：
- `.github/workflows/deploy.yml` - GitHub Actions工作流
- `.gitignore` - Git忽略文件配置

使用步骤：
```bash
# 1. 推送代码到GitHub
git add .
git commit -m "Add GitHub Actions deployment"
git push origin main

# 2. 在GitHub仓库设置中
# Settings → Pages → Source: GitHub Actions
```

## 🌐 访问您的网站

部署成功后，您的网站将在以下地址可用：
```
https://您的用户名.github.io/您的仓库名/
```

## 🔄 更新网站

### 手动更新
```bash
# 1. 重新生成网站
python papertools.py run

# 2. 提交更改
git add webpages/
git commit -m "Update papers: $(date +%Y-%m-%d)"
git push origin main
```

### 自动更新（GitHub Actions）
只需推送任何更改到main分支，GitHub Actions会自动：
1. 检查是否有论文数据
2. 重新生成网站（如果需要）
3. 部署到GitHub Pages

## 📊 网站功能

您部署的网站将包含：
- ✅ 响应式设计，支持移动设备
- ✅ 论文搜索和筛选功能
- ✅ 收藏和已读状态（本地存储）
- ✅ 按日期和分类组织
- ✅ 现代化UI设计

## 🔧 自定义配置

### 修改网站标题
编辑 `src/core/generate_unified_index.py` 中的标题：
```python
<title>您的自定义标题 - 学术论文集合</title>
```

### 添加自定义域名
1. 在仓库根目录创建 `CNAME` 文件
2. 内容为您的域名（如：`myarxiv.example.com`）
3. 在域名提供商处配置DNS

## 🛠️ 故障排除

### 常见问题

1. **网站显示404**
   - 检查GitHub Pages设置中的文件夹是否为 `/webpages`
   - 确保 `webpages/index.html` 存在

2. **样式丢失**
   - 检查网络连接，网站使用CDN加载Tailwind CSS
   - 确保HTML文件中的CDN链接可访问

3. **论文数据不显示**
   - 检查 `summary/` 目录是否包含JSON文件
   - 重新运行 `python src/core/generate_unified_index.py`

### 获取帮助

如遇问题，请检查：
1. GitHub Actions运行日志
2. 浏览器开发者工具控制台
3. GitHub Pages部署状态

## 📈 进阶功能

### 定期自动更新
可以设置GitHub Actions定时任务，定期拉取新论文并更新网站：

```yaml
on:
  schedule:
    - cron: '0 2 * * *'  # 每天凌晨2点运行
  workflow_dispatch:
```

### 多环境部署
- 开发环境：推送到 `dev` 分支
- 生产环境：推送到 `main` 分支

---

🎉 **恭喜！** 您现在可以将学术论文网站分享给全世界了！
