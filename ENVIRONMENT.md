# 项目开发环境

本项目在 Windows 上统一使用 Python 3.10 和本目录下的 `.venv`。虚拟环境、
下载缓存和真实 `.env` 均为本机文件，不提交 Git；依赖声明与锁定文件需要提交。

## 首次创建

在仓库根目录执行：

```powershell
py -3.10 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
```

## 日常使用

```powershell
.venv/Scripts/Activate.ps1
python -m pytest -q
```

- `requirements.txt`：直接运行依赖。
- `requirements-dev.txt`：运行依赖加测试工具。
- `requirements.lock`：Python 3.10/Windows 的完整锁定版本，协作和部署优先使用。
- `.env.example`：配置模板；复制为 `.env` 后填写自己的 API Key，不得提交真实密钥。

UE 5.4、打包程序和 Pixel Streaming Node 环境仍位于 `D:\TQ_Projects\UE_data`
及 `D:\UE_5.4`，不属于 Python 虚拟环境，也不进入本仓库。
