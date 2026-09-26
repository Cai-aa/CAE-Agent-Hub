"""ANSA 25 GUITK dashboard. No model operations are performed by rendering."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .monitor import VERSION

STATUS = {"running": "执行中", "completed": "已返回", "failed": "失败",
          "outcome_unknown": "结果不确定", "replayed": "已返回缓存（未重做）"}
METHOD = {"ping": "连接探测", "get_session_info": "读取会话", "get_model_summary": "模型统计",
          "get_capabilities": "能力查询", "get_step_history": "步骤查询", "get_entity": "读取实体",
          "list_entities": "查询实体", "create_entity": "创建实体", "set_entity_card_values": "修改属性",
          "execute_python_step": "Python 步骤", "save_database": "保存模型", "refresh_view": "刷新视图",
          "run_model_checks": "模型检查"}


class Dashboard:
    def __init__(self, runtime, window):
        from ansa import guitk as g
        self.g, self.runtime = g, runtime
        self.revision = -1
        self.updating = False
        self.selected_sequence = None
        c = g.constants
        root = g.BCBoxLayoutCreate(window, c.BCVertical)
        self.connection = g.BCLabelCreate(root, "启动中 / Starting...")
        self.context = g.BCLabelCreate(root, "正在读取会话...")
        self.status_label = g.BCLabelCreate(root, "等待 MCP 操作 / Waiting for requests")
        tabs = g.BCTabWidgetCreate(root)
        records = g.BCFrameCreate(tabs)
        g.BCTabWidgetAddTab(tabs, records, "记录 / History")
        layout = g.BCBoxLayoutCreate(records, c.BCVertical)
        self.timeline = g.BCListViewCreate(layout, 4, ["#", "操作 / Operation", "状态", "耗时 s"], False)
        g.BCListViewSetSelectionChangedFunction(self.timeline, self._selected, None)
        self.details = self._text(layout, "点击记录查看参数摘要与结果。Python 源码不留存。")
        g.BCBoxLayoutSetStretchFactor(layout, self.timeline, 2)
        g.BCBoxLayoutSetStretchFactor(layout, self.details, 1)
        model = g.BCFrameCreate(tabs)
        g.BCTabWidgetAddTab(tabs, model, "模型 / Model")
        model_layout = g.BCBoxLayoutCreate(model, c.BCVertical)
        self.capture = g.BCCheckBoxCreate(model_layout, "操作前后统计数量（大模型可关闭）")
        g.BCCheckBoxSetChecked(self.capture, True)
        g.BCCheckBoxSetToggledFunction(self.capture, self._capture, None)
        g.BCPushButtonCreate(model_layout, "刷新模型统计 / Refresh", self._refresh_model, None)
        self.model_text = self._text(model_layout, "尚未采样。仅手动刷新或操作前后采样，不循环扫描模型。")
        diagnostics = g.BCFrameCreate(tabs)
        g.BCTabWidgetAddTab(tabs, diagnostics, "诊断 / Diagnostics")
        diagnostic_layout = g.BCBoxLayoutCreate(diagnostics, c.BCVertical)
        self.diagnostic_text = self._text(diagnostic_layout, "暂无错误。")
        g.BCPushButtonCreate(diagnostic_layout, "会话自检 / Session check", self._check, None)
        g.BCPushButtonCreate(diagnostic_layout, "复制诊断 / Copy diagnostics", self._copy, None)
        g.BCPushButtonCreate(diagnostic_layout, "导出记录 JSON / Export", self._export, None)
        self.notice = g.BCLabelCreate(root, "关闭面板会断开桥接；执行完成不代表工程验证通过。")
        g.BCTabWidgetSetCurrentTab(tabs, records)
        g.BCBoxLayoutSetStretchFactor(root, tabs, 1)
        g.BCWindowSetSize(window, 540, 740)

    def _text(self, parent, text):
        widget = self.g.BCTextEditCreate(parent, "")
        self.g.BCTextEditSetReadOnly(widget, True)
        self._set_text(widget, text)
        return widget

    def _set_text(self, widget, text):
        # Insert literal text, not automatically interpreted rich text.
        self.g.BCTextEditClear(widget)
        self.g.BCTextEditInsert(widget, str(text))

    def tick(self):
        m = self.runtime.monitor
        age = "尚无认证请求" if m.last_request_clock is None else f"最近认证请求 {int(time.monotonic() - m.last_request_clock)} 秒前"
        state = "监听就绪" if self.runtime.state == "online" else self.runtime.state
        self.g.BCLabelSetText(self.connection, f"{state} | 127.0.0.1:{self.runtime.port}\n{age} | 运行 {int(time.monotonic() - m.started)} 秒")
        s = m.session
        filename = Path(s["database"]).name if s.get("database") else "未命名 / Empty"
        self.g.BCLabelSetText(self.context, f"ANSA {s.get('version', '?')} | Runtime {VERSION} | PID {s.get('pid', '?')}\n{s.get('deck_name', '?')} | {filename[:65]}")
        if self.revision == m.revision:
            return
        self.revision = m.revision
        self.updating = True
        try:
            self.g.BCListViewClear(self.timeline)
            for event in reversed(m.events):
                label = str(event['label']) if event['method'] == 'execute_python_step' else METHOD.get(event['method'], event['method'])
                values = [str(event['sequence']), label[:80], STATUS[event['status']], str(event.get('elapsed_seconds', '—'))]
                item = self.g.BCListViewAddItem(self.timeline, 4, values, [self.g.constants.BCRenameType_None] * 4)
                self.g.BCListViewItemSetUserData(item, event['sequence'])
            selected = next((e for e in m.events if e['sequence'] == self.selected_sequence), None)
            if selected is None and m.events:
                selected = m.events[-1]
            if selected:
                self._set_text(self.details, json.dumps(selected, ensure_ascii=False, indent=2))
            if m.events:
                e = m.events[-1]
                self.g.BCLabelSetText(self.status_label, f"#{e['sequence']} {str(e['label'])[:65]}\n{STATUS[e['status']]} | {e.get('elapsed_seconds', '—')} s")
            self._set_text(self.model_text, self._model_summary())
            errors = "\n\n".join(f"{e['at']} [{e['source']}]\n{e['message']}" for e in m.errors)
            self._set_text(self.diagnostic_text, f"最近认证请求：{m.last_request_at or '无'}\n已记录请求：{m.sequence}（保留最近 100 条）\n\n{errors or '暂无错误。'}\n\n源码和任意 Python 返回值不入日志；分享前请检查路径及参数。")
        finally:
            self.updating = False

    def _model_summary(self):
        m = self.runtime.monitor
        s = m.model
        if not s:
            return "尚未采样。点击刷新；默认在修改操作前后采样。"
        lines = [f"采样：{s.get('sampled_at', '?')}", f"文件：{s.get('database', '') or '未命名'}", f"Deck：{s.get('deck_name', '?')}"]
        lines.extend(f"{k}: {v:,}" for k, v in s.get('counts', {}).items())
        if s.get('error') or s.get('errors'):
            lines.append("部分统计不可用：" + str(s.get('error') or s['errors']))
        change = m.last_change
        if change:
            lines.extend(["", "最近一步数量变化：" + change['status']])
            for k, v in change.get('counts', {}).items():
                lines.append(f"{k}: {v['before']:,} → {v['after']:,} ({v['delta']:+,})")
        lines.extend(["", "数量不变不代表属性/几何未改变。", "模型快照不是实时同步；手动操作后请刷新。", "数量统计不等于网格质量或工程验证。"])
        return "\n".join(lines)

    def _selected(self, widget, data):
        if self.updating:
            return 0
        item = self.g.BCListViewGetSelectedItem(widget)
        if item:
            self.selected_sequence = self.g.BCListViewItemGetUserData(item)
            event = next((e for e in self.runtime.monitor.events if e['sequence'] == self.selected_sequence), None)
            if event:
                self._set_text(self.details, json.dumps(event, ensure_ascii=False, indent=2))
        return 0

    def _capture(self, widget, state, data):
        self.runtime.monitor.capture_changes = bool(self.g.BCCheckBoxIsChecked(widget))
        return 0

    def _refresh_model(self, button, data):
        self.runtime.refresh_model_snapshot()
        self.tick()
        return 0

    def _check(self, button, data):
        ok = self.runtime.refresh_session()
        self.g.BCLabelSetText(self.notice, "会话读取成功；认证请求请看顶部，不代表求解验证。" if ok else "会话读取失败，请查看诊断。")
        self.tick()
        return 0

    def _copy(self, button, data):
        try:
            report = self.runtime.monitor.export()
            report.pop('events', None)
            self.g.BCApplicationClipboardSetText(json.dumps(report, ensure_ascii=False, indent=2))
            self.g.BCLabelSetText(self.notice, "诊断已复制；分享前请检查文件路径。")
        except Exception as exc:
            self.runtime._log_error('copy-diagnostics', exc)
        return 0

    def _export(self, button, data):
        try:
            path = self.runtime.export_monitor()
            self.g.BCLabelSetText(self.notice, "已导出记录：" + path.name)
            print("ANSA MCP diagnostic export: " + str(path))
        except Exception as exc:
            self.runtime._log_error('export-diagnostics', exc)
            self.g.BCLabelSetText(self.notice, "导出失败，请看诊断页。")
        self.tick()
        return 0
