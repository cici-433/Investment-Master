# Investment Master 网站部署指南

本文档详细介绍了如何将 Investment Master 项目部署到 **PythonAnywhere** 免费云托管平台。

---

## 目录
1. [前期准备](#1-前期准备)
2. [注册与环境设置](#2-注册与环境设置)
3. [拉取代码与安装依赖](#3-拉取代码与安装依赖)
4. [配置 Web 应用](#4-配置-web-应用)
5. [数据同步](#5-数据同步)
6. [常见问题与维护](#6-常见问题与维护)

---

## 1. 前期准备

在开始之前，请确保：
*   项目代码已提交到 GitHub（包含 `requirements.txt` 和 `app.py`）。
*   **注意**：PythonAnywhere 免费版无法访问某些外部 API（如新浪财经），本项目已做特殊适配（优先读取本地 JSON 数据）。

---

## 2. 注册与环境设置

1.  访问 [PythonAnywhere 官网](https://www.pythonanywhere.com/)。
2.  点击 **Sign up** -> **Create a Beginner account** (免费版)。
3.  填写用户名、邮箱和密码注册。
    *   *提示：您的网站地址将是 `https://您的用户名.pythonanywhere.com`*

---

## 3. 拉取代码与安装依赖

1.  登录后，点击右上角的 **Consoles** 标签。
2.  点击 **Bash** 启动一个命令行终端。
3.  在黑色终端窗口中，依次执行以下命令：

```bash
# 1. 克隆代码仓库 (将 URL 替换为您的 GitHub 地址)
git clone https://github.com/cici-433/Investment-Master.git

# 2. 进入项目目录
cd Investment-Master

# 3. 安装依赖包 (注意加上 --user 参数)
pip install -r requirements.txt --user
```

*等待安装完成（通常需要 1-2 分钟）。*

---

## 4. 配置 Web 应用

1.  点击页面右上角的 **Web** 标签。
2.  点击 **Add a new web app** -> **Next**。
3.  选择框架：**Flask**。
4.  选择版本：**Python 3.10** (建议)。
5.  **关键步骤：设置路径**
    *   在 "Path" 输入框中，**手动修改**为：
        `/home/您的用户名/Investment-Master/app.py`
    *   *注意：请将“您的用户名”替换为实际显示的用户名，确保路径指向刚才下载的文件夹。*
6.  点击 **Next** 完成创建。

此时，您的网站应该已经可以访问了（显示 Investment Master 主页）。

---

## 5. 数据同步

为了让网站显示您本地的持仓、日志和文章数据，我们需要同步 JSON 数据文件。

### 方法 A：通过 GitHub 同步 (推荐)
如果您的 `data/*.json` 文件已经提交到了 GitHub：
1.  在 PythonAnywhere 的 **Bash** 控制台中运行：
    ```bash
    cd ~/Investment-Master
    git pull
    ```
2.  数据会自动更新。

### 方法 B：手动上传 (如果不方便用 Git)
1.  点击右上角的 **Files** 标签。
2.  进入 `Investment-Master` -> `data` 目录。
3.  使用 **Upload a file** 按钮，上传您本地的 `portfolio.json`, `investment_journal.json`, `investment_system.json`。

---

## 6. 常见问题与维护

### Q: 网站显示 "Something went wrong"？
*   **查看日志**：去 **Web** 页面，找到 **Log files** -> **Error log**，查看具体报错。
*   **检查依赖**：确认是否执行了 `pip install -r requirements.txt --user`。

### Q: 怎么更新代码？
如果您在本地修改了代码并推送到 GitHub，只需在服务器上更新即可：
1.  打开 **Consoles** -> **Bash**。
2.  运行更新命令：
    ```bash
    cd ~/Investment-Master
    git pull
    # 触发自动重启
    touch /var/www/您的用户名_pythonanywhere_com_wsgi.py
    ```

### Q: 中文股票名称不显示？
*   PythonAnywhere 免费版限制了对新浪财经接口的访问。
*   本项目已优化：只要您在本地运行过并保存了数据（有了中文名），上传 `portfolio.json` 后，服务器会自动读取本地保存的中文名进行显示。

---

**祝您的投资复盘系统运行顺利！**
