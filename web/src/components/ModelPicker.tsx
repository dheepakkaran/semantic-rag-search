import { useEffect, useRef, useState } from "react";

import type { Provider } from "../types";

interface Props {
  providers: Provider[];
  /** null means Auto: walk the chain and fall back on refusal. */
  selected: string | null;
  onSelect: (provider: string | null) => void;
}

/**
 * A text button that opens a short list. Deliberately not a `<select>`: the
 * native control cannot show a second line per option, and "which models have
 * a key" is the part worth showing.
 */
export function ModelPicker({ providers, selected, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function onDocumentPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", onDocumentPointerDown);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("pointerdown", onDocumentPointerDown);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  const current = providers.find((p) => p.name === selected);
  const label = current ? current.name : "Auto";

  function choose(provider: string | null) {
    onSelect(provider);
    setOpen(false);
  }

  return (
    <div className="picker" ref={root}>
      <button
        type="button"
        className="picker-button"
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <span className={selected ? "dot pinned" : "dot"} aria-hidden="true" />
        {label}
      </button>

      {open && (
        <div className="picker-menu rise-sm" role="listbox">
          <button
            type="button"
            role="option"
            aria-selected={selected === null}
            className={selected === null ? "picker-option on" : "picker-option"}
            onClick={() => choose(null)}
          >
            <span className="picker-name">Auto</span>
            <span className="picker-sub">try each in turn, fall back if refused</span>
          </button>

          {providers.map((provider) => (
            <button
              key={provider.name}
              type="button"
              role="option"
              aria-selected={selected === provider.name}
              disabled={!provider.ready}
              className={
                selected === provider.name ? "picker-option on" : "picker-option"
              }
              onClick={() => choose(provider.name)}
            >
              <span className="picker-name">
                {provider.name}
                {!provider.ready && <span className="picker-tag">no key</span>}
              </span>
              <span className="picker-sub">{provider.model}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
