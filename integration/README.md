# 在 Ubuntu 上接入现有工作台

此增量适用于已取得原壁画工作台源码的团队，验证基线为 cf2be17。建议在独立工作副本上安装，保留原实例及未保存的浏览器进度。

在本仓库根目录，设置 BASE 为原工作台工作副本的绝对路径，再运行：

```bash
git -C "$BASE" apply --check "$PWD/integration/workbench.patch" &&
git -C "$BASE" apply "$PWD/integration/workbench.patch" &&
cp static/region-evidence.js static/region-evidence.css static/workspace.js static/workspace.css "$BASE/static/" &&
cp -R static/vendor "$BASE/static/"
```

使用原工作台配置的 Python 环境及依赖。在 BASE 目录运行 `PORT=8766 python app.py`，浏览器打开 http://localhost:8766 。实例只监听回环地址，适合同一台电脑轮流试用。模型凭据继续由原工作台的配置机制管理。

在本仓库根目录，用含原工作台测试依赖的 Python 运行 `PYTHONPATH="$BASE" python -m unittest discover -s tests`。工作文件 v1/v2 可恢复后补录依据；新文件使用 v3，保留每个区域的引用和复核记录。旧客户端仍可导出原格式观察卡。

工作台导入框可选择 JPEG、PNG、WebP 图片或 JSON 工作文件。若要启用一键试用，将可供本机队员查看的练习工作文件放在工作副本的 `sample/evidence-trial.json`；首页会显示“打开试用工作文件”，也可直接访问 `/?trial=evidence`。


## 界面与字体

观察区使用定高分栏，区域按钮切换当前编辑项，保护建议在独立面板编辑。裁片弹窗采用原生 dialog，图片按自身比例显示，说明独立滚动；Panzoom 4.6.2 支持缩放和平移。修复区可切换局部与全图，并放大并排核对。新图片在 LaMa 可用且允许时默认选择它，恢复的工作文件保留其处理方法。

字体优先使用队员电脑已经安装的方正书宋简体和华文楷体，依次回退到华文宋体、宋体、楷体及系统衬线字体。字体文件由各自设备提供。公开仓库包含 CSS 字体配置，Panzoom 的 MIT 许可证与发行文件位于同一目录。

2026 年 11 月 20 日，用 1440、1024、390 像素视口验证了区域切换、建议面板、弹窗裁片尺寸、缩放、关闭按钮与页面溢出。另从浏览器实际调用 LaMa 处理合成图的跨边框区域，验证范围外像素一致、局部/全图切换与单页报告导出。该合成测试反映此例的工程行为，真实题图逐处复核后采纳。
