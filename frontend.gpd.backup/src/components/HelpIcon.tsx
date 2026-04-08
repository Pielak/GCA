/**
 * HelpIcon — ícone "?" com tooltip de ajuda contextual.
 * Exibido sempre abaixo e à direita do ícone.
 * Uso: <HelpIcon text="Explicação da funcionalidade..." />
 */
import { useState, useRef, useEffect } from "react";
import { HelpCircle } from "lucide-react";

interface HelpIconProps {
  text: string;
}

export function HelpIcon({ text }: HelpIconProps) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  // Fecha ao clicar fora
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (
        btnRef.current && !btnRef.current.contains(e.target as Node) &&
        tipRef.current && !tipRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Calcula posição do tooltip relativa ao viewport e ajusta para não vazar
  const [tipStyle, setTipStyle] = useState<React.CSSProperties>({});

  useEffect(() => {
    if (!open || !btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const tipWidth = 288; // w-72
    const margin = 8;

    let left = rect.left;
    // Se vazar pela direita, empurra para a esquerda
    if (left + tipWidth > window.innerWidth - margin) {
      left = window.innerWidth - tipWidth - margin;
    }
    // Garante que não sai pela esquerda
    if (left < margin) left = margin;

    setTipStyle({
      position: "fixed",
      top: rect.bottom + 6,
      left,
      width: tipWidth,
    });
  }, [open]);

  return (
    <span className="relative inline-flex items-center ml-1.5">
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-violet-400 hover:text-violet-300 focus:outline-none"
        aria-label="Ajuda"
      >
        <HelpCircle size={16} />
      </button>

      {open && (
        <div
          ref={tipRef}
          style={tipStyle}
          className="z-[9999] rounded-lg bg-gray-800 border border-gray-600 p-3 text-xs text-gray-200 shadow-xl leading-relaxed"
        >
          {text}
        </div>
      )}
    </span>
  );
}
