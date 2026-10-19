# 中文字体文件

PDF 报告生成（fpdf2）需要中文字体才能正确渲染汉字。

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

`generate_pdf()` 按以下顺序查找字体：

1. 此目录下的 `*.ttf` 文件
2. `/usr/share/fonts/truetype/wqy/wqy-microhei.ttc`（apt 安装后）
3. `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`
4. 如果都找不到 → 降级为纯文本输出（不生成 PDF）