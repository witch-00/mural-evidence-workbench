# 在 Ubuntu 上接入现有工作台

此增量适用于已取得原壁画工作台源码的团队，验证基线为 cf2be17。建议在独立工作副本上安装，保留原实例及未保存的浏览器进度。

在本仓库根目录，设置 BASE 为原工作台工作副本的绝对路径，再运行：

```bash
git -C "$BASE" apply --check "$PWD/integration/workbench.patch" &&
git -C "$BASE" apply "$PWD/integration/workbench.patch" &&
cp static/region-evidence.js static/region-evidence.css "$BASE/static/"
```

使用原工作台配置的 Python 环境及依赖。在 BASE 目录运行 `PORT=8766 python app.py`，浏览器打开 http://localhost:8766 。实例只监听回环地址，适合同一台电脑轮流试用。模型凭据继续由原工作台的配置机制管理。

在本仓库根目录，用含原工作台测试依赖的 Python 运行 `PYTHONPATH="$BASE" python -m unittest discover -s tests`。工作文件 v1/v2 可恢复后补录依据；新文件使用 v3，保留每个区域的引用和复核记录。旧客户端仍可导出原格式观察卡。
