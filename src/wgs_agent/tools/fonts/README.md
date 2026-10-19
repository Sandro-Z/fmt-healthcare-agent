# 中文字体文件

PDF 报告生成（fpdf2）需要中文字体才能正确渲染汉字。健康报告的实际查找逻辑位于
`wgs_agent/reporting/fonts.py`，支持系统 Noto CJK，无需复制商业字体。

## 推荐下载方式

```bash
# 方式 1：apt 安装（需要 sudo）
sudo apt install -y fonts-wqy-microhei

# 方式 2：手动下载 Noto Sans SC 放到此目录
cd src/wgs_agent/tools/fonts
wget https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf \
  -O NotoSansSC.ttf
```

## 字体搜索优先级

健康报告按以下顺序查找字体：

1. `WGS_REPORT_FONT_REGULAR` 和可选的 `WGS_REPORT_FONT_BOLD`
2. 此目录的 `MSYH.TTC/MSYHBD.TTC` 或 `NotoSansSC.ttf/NotoSansSC-Bold.ttf`
3. `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` 和对应粗体
4. `/usr/share/fonts/truetype/wqy/wqy-microhei.ttc`
5. 都找不到时返回生成错误，保留上一版报告，避免用旧 PDF 冒充本次结果
