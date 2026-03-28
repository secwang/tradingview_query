PYTHON  := python3
SCRIPT  := tv.py
CACHE   := tv_user_data
REPORTS := TradingView_Reports

.PHONY: run run-hl pdf pdf-hl cache cache-pdf setup clean clean-cache clean-reports help

help:
	@echo "用法: make <目标>"
	@echo ""
	@echo "  run           抓取截图，生成 HTML 报告（有头浏览器）"
	@echo "  run-hl        抓取截图，生成 HTML 报告（无头模式）"
	@echo "  pdf           抓取截图，生成 PDF 报告（有头浏览器）"
	@echo "  pdf-hl        抓取截图，生成 PDF 报告（无头模式）"
	@echo "  cache         使用本地截图，重新生成 HTML 报告"
	@echo "  cache-pdf     使用本地截图，重新生成 PDF 报告"
	@echo "  setup         手动登录 / 调整 TradingView 后回车确认"
	@echo ""
	@echo "  clean         清理浏览器缓存 + 报告目录（全部删除）"
	@echo "  clean-cache   仅清理浏览器缓存目录 ($(CACHE))"
	@echo "  clean-reports 仅清理报告输出目录 ($(REPORTS))"

run:
	$(PYTHON) $(SCRIPT) html

run-hl:
	$(PYTHON) $(SCRIPT) html --headless

pdf:
	$(PYTHON) $(SCRIPT) pdf

pdf-hl:
	$(PYTHON) $(SCRIPT) pdf --headless

cache:
	$(PYTHON) $(SCRIPT) html --cache

cache-pdf:
	$(PYTHON) $(SCRIPT) pdf --cache

setup:
	$(PYTHON) $(SCRIPT) setup

clean:
	$(PYTHON) $(SCRIPT) clean

clean-cache:
	@rm -rf $(CACHE) && echo "✅ 浏览器缓存已清理 ($(CACHE))"

clean-reports:
	@rm -rf $(REPORTS) && echo "✅ 报告目录已清理 ($(REPORTS))"
