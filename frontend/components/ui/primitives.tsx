/**
 * The tiny Vednix design-system primitives (shadcn-style: owned, tweakable).
 * Kept in one file on purpose — each is < 40 lines and they share tokens.
 */

"use client";

import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/* --- Button ----------------------------------------------------------------- */

type ButtonVariant = "primary" | "ghost" | "subtle" | "danger";
type ButtonSize = "sm" | "md" | "icon";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const buttonVariants: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-b from-[#f4d68a] to-[#d9a83f] text-[#1c1505] font-semibold shadow-[0_4px_20px_-6px_rgba(227,184,87,0.7)] hover:shadow-[0_4px_26px_-4px_rgba(227,184,87,0.9)] hover:brightness-105 active:scale-[0.98]",
  ghost: "text-muted hover:text-cream hover:bg-white/[0.05]",
  subtle: "glass text-cream hover:border-[rgba(227,184,87,0.35)] hover:text-gold-bright",
  danger: "text-[#f0746e] hover:bg-[rgba(240,86,79,0.12)]",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs rounded-lg gap-1.5",
  md: "h-10 px-4 text-sm rounded-xl gap-2",
  icon: "h-8 w-8 rounded-lg",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "ghost", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap transition-all duration-150",
        "focus-visible:outline-2 focus-visible:outline-gold/60 disabled:pointer-events-none disabled:opacity-40",
        buttonVariants[variant],
        buttonSizes[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";

/* --- GlassPanel ---------------------------------------------------------------- */

export function GlassPanel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass rounded-2xl", className)} {...props} />;
}

/* --- Badge -------------------------------------------------------------------- */

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[rgba(227,184,87,0.25)] bg-[rgba(227,184,87,0.08)]",
        "px-2 py-0.5 text-[10px] font-medium tracking-wide text-gold/90 uppercase",
        className,
      )}
      {...props}
    />
  );
}

/* --- Segmented control ---------------------------------------------------------- */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={cn("glass flex rounded-xl p-1 gap-0.5", className)}>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "flex-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-150",
            value === opt.value
              ? "bg-[rgba(227,184,87,0.18)] text-gold-bright shadow-[inset_0_0_0_1px_rgba(227,184,87,0.35)]"
              : "text-muted hover:text-cream",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/* --- Slider --------------------------------------------------------------------- */

export function Slider({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="range"
      className={cn(
        "h-1.5 w-full cursor-pointer appearance-none rounded-full bg-edge outline-none",
        "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4",
        "[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-gradient-to-b",
        "[&::-webkit-slider-thumb]:from-[#f4d68a] [&::-webkit-slider-thumb]:to-[#d9a83f]",
        "[&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(227,184,87,0.6)]",
        className,
      )}
      {...props}
    />
  );
}

/* --- Switch ---------------------------------------------------------------------- */

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  label,
}: {
  checked: boolean;
  onCheckedChange?: (v: boolean) => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        "relative h-5.5 w-10 shrink-0 rounded-full transition-colors duration-200 h-[22px]",
        checked ? "bg-gradient-to-r from-[#d9a83f] to-[#e3b857]" : "bg-edge",
        disabled && "cursor-not-allowed opacity-35",
      )}
    >
      <span
        className={cn(
          "absolute top-1/2 h-[16px] w-[16px] -translate-y-1/2 rounded-full bg-[#fff7e6] shadow transition-all duration-200",
          checked ? "left-[22px]" : "left-[3px]",
        )}
      />
    </button>
  );
}

/* --- Input ------------------------------------------------------------------------- */

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "glass h-9 w-full rounded-xl px-3 text-sm text-cream placeholder:text-faint",
        "outline-none transition-colors focus:border-[rgba(227,184,87,0.4)]",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
