/**
 * Shared attachment UI + helpers — extracted from Composer (MessageBubble
 * rendered attachments by importing the composer, an architectural smell).
 * Now both views draw from one chat-domain module.
 */

"use client";

import { FileText, Image as ImageIcon, Table2, Presentation, FileCode, X } from "lucide-react";
import type { AttachmentChip } from "@/store/chat";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function kindIcon(kind: string) {
  switch (kind) {
    case "image": return ImageIcon;
    case "sheet": return Table2;
    case "slides": return Presentation;
    case "text": return FileCode;
    default: return FileText;
  }
}

export function AttachmentChipView({ att, onRemove }: { att: AttachmentChip; onRemove?: () => void }) {
  const Icon = kindIcon(att.kind);
  return (
    <span className="glass group/chip flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-xs text-cream/85">
      <Icon className="h-3.5 w-3.5 text-gold/80" />
      <span className="max-w-[160px] truncate">{att.name}</span>
      <span className="text-faint">{formatBytes(att.size)}</span>
      {onRemove && (
        <button
          aria-label={`Remove ${att.name}`}
          onClick={onRemove}
          className="rounded-full p-0.5 text-faint transition-colors duration-300 hover:bg-white/10 hover:text-danger"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  );
}
