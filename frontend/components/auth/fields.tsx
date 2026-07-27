/**
 * Auth form atoms — labelled glass inputs with animated error states, a
 * password field with reveal toggle, animated inline error banners, and the
 * gold submit button with loading morph. Shared by /login and /signup so the
 * two pages never drift apart.
 */

"use client";

import { forwardRef, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  invalid?: boolean;
  trailing?: ReactNode;
}

const inputBase =
  "glass w-full rounded-xl px-3.5 text-sm text-cream placeholder:text-faint " +
  "focus:outline-none focus:border-gold/40 focus:ring-1 focus:ring-gold/20 " +
  "transition-all duration-200 disabled:opacity-50";

export const AuthField = forwardRef<HTMLInputElement, FieldProps>(function AuthField(
  { label, hint, invalid, trailing, className, id, ...props },
  ref,
) {
  const fieldId = id ?? label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="space-y-1.5">
      <label htmlFor={fieldId} className="block font-mono text-[10px] uppercase tracking-[0.2em] text-faint">
        {label}
      </label>
      <div className="relative">
        <motion.input
          ref={ref}
          id={fieldId}
          aria-invalid={invalid || undefined}
          className={cn(inputBase, "h-11", trailing && "pr-11", className)}
          animate={invalid ? { x: [0, -6, 6, -3, 0] } : { x: 0 }}
          transition={{ duration: 0.35 }}
          {...(props as object)}
        />
        {trailing && <div className="absolute right-2 top-1/2 -translate-y-1/2">{trailing}</div>}
      </div>
      {hint && <p className="text-[11px] leading-relaxed text-faint">{hint}</p>}
    </div>
  );
});

export function PasswordField(props: Omit<FieldProps, "type" | "trailing">) {
  const [show, setShow] = useState(false);
  return (
    <AuthField
      {...props}
      type={show ? "text" : "password"}
      trailing={
        <button
          type="button"
          tabIndex={-1}
          aria-label={show ? "Hide password" : "Show password"}
          onClick={() => setShow((s) => !s)}
          className="rounded-md p-1.5 text-faint transition-colors hover:text-cream"
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      }
    />
  );
}

export function AuthError({ message }: { message: string | null }) {
  return (
    <AnimatePresence initial={false}>
      {message && (
        <motion.div
          role="alert"
          className="flex items-start gap-2.5 rounded-xl border border-[#f0746e]/30 bg-[#f0746e]/[0.07] px-3.5 py-3 text-[13px] leading-relaxed text-[#f49a96]"
          initial={{ opacity: 0, y: -8, height: 0 }}
          animate={{ opacity: 1, y: 0, height: "auto" }}
          exit={{ opacity: 0, y: -6, height: 0 }}
          transition={{ duration: 0.28 }}
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{message}</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function AuthSubmit({
  loading,
  children,
  disabled,
}: {
  loading: boolean;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <Button
      type="submit"
      variant="primary"
      size="md"
      disabled={loading || disabled}
      className="h-11 w-full rounded-xl text-sm"
    >
      {loading ? (
        <span className="inline-flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          One moment…
        </span>
      ) : (
        children
      )}
    </Button>
  );
}

/** Small mono checkbox row (remember me / terms) with a gold check state. */
export function AuthCheck({
  checked,
  onChange,
  id,
  children,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  id: string;
  children: ReactNode;
}) {
  return (
    <label htmlFor={id} className="group flex cursor-pointer select-none items-start gap-2.5">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="peer sr-only"
      />
      <span
        aria-hidden
        className={cn(
          "mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[6px] border transition-all duration-200",
          checked
            ? "border-gold/60 bg-gold/20 text-gold-bright shadow-[0_0_8px_rgba(227,184,87,0.25)]"
            : "border-white/15 bg-white/[0.03] text-transparent group-hover:border-gold/30",
        )}
      >
        <svg viewBox="0 0 10 8" className="h-2 w-2.5 fill-current">
          <path d="M1 4l2.5 2.5L9 1" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        </svg>
      </span>
      <span className="text-[13px] leading-snug text-muted peer-checked:text-cream">{children}</span>
    </label>
  );
}
