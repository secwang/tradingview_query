PYTHON  := python3
SCRIPT  := tv.py
CACHE   := tv_user_data
REPORTS := TradingView_Reports

.PHONY: run setup pdf cache cache-pdf clean clean-cache clean-reports help

## 默认目标
help:
	@echo "用法: make <目标>"
	@echo ""
	@echo "  run            联网抓取 Watchlist，生成 HTML 报告并打开"
	@echo "  setup          设置模式（打开浏览器，手动登录/调整后回车）"
	@echo "  pdf            联网抓取 Watchlist，生成 PDF + HTML 报告"
	@echo "  cache          使用本地截图缓存，重新生成 HTML 报告"
	@echo "  cache-pdf      使用本地截图缓存，重新生成 PDF + HTML 报告"
	@echo ""
	@echo "  clean          清理浏览器缓存 + 报告目录（全部删除）"
	@echo "  clean-cache    仅清理浏览器缓存目录 ($(CACHE))"
	@echo "  clean-reports  仅清理报告输出目录 ($(REPORTS))"

## 运行模式
run:
	$(PYTHON) $(SCRIPT)

setup:
	$(PYTHON) $(SCRIPT) setup

pdf:
	$(PYTHON) $(SCRIPT) pdf

cache:
	$(PYTHON) $(SCRIPT) --cache

cache-pdf:
	$(PYTHON) $(SCRIPT) --cache pdf

## 清理
clean:
	$(PYTHON) $(SCRIPT) clean

clean-cache:
	@rm -rf $(CACHE) && echo "✅ 浏览器缓存已清理 ($(CACHE))"

clean-reports:
	@rm -rf $(REPORTS) && echo "✅ 报告目录已清理 ($(REPORTS))"
