/**
 * The Blockly workspace (station-programs.md §5, P3). Lazy-loaded by the program screen (its own
 * chunk), so the rest of Station never downloads Blockly. The browser never executes a program:
 * this component only edits the workspace JSON, which the Station compiles (`PUT /programs/{id}`).
 *
 * Live view: `highlight` is the block the runner executes (`program_state.block_id`), `issues` puts
 * a warning icon with the localised text on every block a check flagged (not for information).
 */
import * as Blockly from "blockly/core";
import "blockly/blocks";
import * as En from "blockly/msg/en";
import * as Vi from "blockly/msg/vi";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/lib/theme";
import type { BlockCatalog, CheckIssue } from "../../api/types";
import { defineCatalog } from "./definitions";
import { setEditorRefs, type EditorRefs } from "./refs";
import type { EditorDoc } from "./serialize";
import { hibiscusTheme, registerRenderer, RENDERER, type ToolboxCategory } from "./theme";
import { buildToolbox, VARIABLES_CALLBACK, variablesFlyout } from "./toolbox";
import "./blockly.css";

export interface BlocklyEditorProps {
  catalog: BlockCatalog;
  refs: EditorRefs;
  /** The document to show. It is (re)loaded whenever `docKey` changes. */
  doc: EditorDoc;
  docKey: string;
  onChange: (doc: EditorDoc) => void;
  highlight?: string | null;
  issues?: CheckIssue[];
  readOnly?: boolean;
  /** Text shown on a block for an issue (localised by the caller). */
  issueText?: (issue: CheckIssue) => string;
  /** Called once the workspace exists (tests and the screen's zoom buttons). */
  onReady?: (ws: Blockly.WorkspaceSvg | null) => void;
}

/** Blockly language packs for the built-in blocks and menus. */
const LOCALES: Record<string, Record<string, string>> = {
  en: En as unknown as Record<string, string>,
  vi: Vi as unknown as Record<string, string>,
};

export function setBlocklyLocale(lang: string): void {
  Blockly.setLocale(LOCALES[lang.startsWith("vi") ? "vi" : "en"] ?? {});
}

export default function BlocklyEditor({
  catalog,
  refs,
  doc,
  docKey,
  onChange,
  highlight = null,
  issues = [],
  readOnly = false,
  issueText,
  onReady,
}: BlocklyEditorProps) {
  const { t, i18n } = useTranslation("station");
  const { resolved } = useTheme();
  const host = useRef<HTMLDivElement>(null);
  const [ws, setWs] = useState<Blockly.WorkspaceSvg | null>(null);
  const latest = useRef<{ key: string; doc: EditorDoc } | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const themeRef = useRef(resolved);
  themeRef.current = resolved;
  setEditorRefs(refs);
  const lang = i18n.language;

  // The workspace is rebuilt when the catalogue, the language or the document changes. A language
  // switch keeps the unsaved edits (the latest document of the same key).
  useEffect(() => {
    const el = host.current;
    if (!el) return undefined;
    const tr = (key: string, fallback: string) => t(key, { defaultValue: fallback });
    setBlocklyLocale(lang);
    defineCatalog(catalog, tr);
    registerRenderer();
    const start = latest.current?.key === docKey ? latest.current.doc : doc;
    const w = Blockly.inject(el, {
      toolbox: buildToolbox(catalog, {
        category: (c: ToolboxCategory) => t(`programs.toolbox.${c}`),
      }) as unknown as Blockly.utils.toolbox.ToolboxDefinition,
      theme: hibiscusTheme(themeRef.current),
      renderer: RENDERER,
      media: "/blockly-media/",
      sounds: false,
      trashcan: true,
      grid: {
        spacing: 24,
        length: 2,
        colour: themeRef.current === "dark" ? "#2b3253" : "#c99a62",
        snap: true,
      },
      zoom: { controls: true, wheel: false, pinch: true, startScale: 0.9, maxScale: 2, minScale: 0.4 },
      move: { scrollbars: true, drag: true, wheel: true },
      maxBlocks: 2000,
    });
    w.registerToolboxCategoryCallback(
      VARIABLES_CALLBACK,
      (target) =>
        variablesFlyout(
          catalog,
          target
            .getVariableMap()
            .getAllVariables()
            .map((v) => ({ id: v.getId(), name: v.getName(), type: v.getType() })),
          { newNumber: t("programs.editor.new_number_var"), newText: t("programs.editor.new_text_var") },
        ) as unknown as Blockly.utils.toolbox.FlyoutDefinition,
    );
    w.registerButtonCallback("hb_new_number", (b) => {
      Blockly.Variables.createVariableButtonHandler(b.getTargetWorkspace(), undefined, "Number");
    });
    w.registerButtonCallback("hb_new_text", (b) => {
      Blockly.Variables.createVariableButtonHandler(b.getTargetWorkspace(), undefined, "String");
    });
    Blockly.Events.disable();
    try {
      Blockly.serialization.workspaces.load(start, w);
    } catch {
      w.clear();
    } finally {
      Blockly.Events.enable();
    }
    latest.current = { key: docKey, doc: start };
    w.addChangeListener((e: Blockly.Events.Abstract) => {
      if (e.isUiEvent || e.type === String(Blockly.Events.FINISHED_LOADING)) return;
      const saved = Blockly.serialization.workspaces.save(w) as EditorDoc;
      latest.current = { key: docKey, doc: saved };
      onChangeRef.current(saved);
    });
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => Blockly.svgResize(w)) : null;
    ro?.observe(el);
    setWs(w);
    onReadyRef.current?.(w);
    return () => {
      ro?.disconnect();
      onReadyRef.current?.(null);
      setWs(null);
      w.dispose();
    };
    // `doc` is read only when `docKey` changes (a new program); `t` follows `lang`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, lang, docKey]);

  useEffect(() => {
    ws?.setTheme(hibiscusTheme(resolved));
  }, [ws, resolved]);

  useEffect(() => {
    if (!ws) return;
    ws.setIsReadOnly(readOnly);
  }, [ws, readOnly]);

  useEffect(() => {
    if (!ws) return;
    const block = highlight ? ws.getBlockById(highlight) : null;
    ws.highlightBlock(block ? block.id : null);
    // Keep the running block on screen (a narrow window shows only part of the program).
    if (block && !ws.isDragging()) ws.scrollBoundsIntoView(block.getBoundingRectangleWithoutChildren(), 24);
  }, [ws, highlight]);

  useEffect(() => {
    if (!ws) return;
    for (const b of ws.getAllBlocks(false)) b.setWarningText(null);
    for (const issue of issues) {
      // Information (D-24) is not a problem: no warning triangle on the block.
      if (issue.severity === "info") continue;
      const b = issue.block_id ? ws.getBlockById(issue.block_id) : null;
      if (b) b.setWarningText(issueText ? issueText(issue) : issue.code, issue.id);
    }
  }, [ws, issues, issueText]);

  return (
    <div
      ref={host}
      className="hb-blockly h-full min-h-[24rem] w-full"
      data-testid="blockly-editor"
      data-readonly={readOnly}
      aria-label={t("programs.editor.workspace")}
      role="region"
    />
  );
}
