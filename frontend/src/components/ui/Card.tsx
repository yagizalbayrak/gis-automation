import { motion } from "motion/react";
import type { ReactNode } from "react";

interface CardProps {
  title: string;
  icon?: ReactNode;
  right?: ReactNode;
  tone?: "default" | "error";
  children: ReactNode;
}

export function Card({ title, icon, right, tone = "default", children }: CardProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className={`rounded-2xl border p-4 backdrop-blur-xl ${
        tone === "error" ? "border-fail/25 bg-fail/[0.06]" : "border-border bg-white/[0.02]"
      }`}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
          {icon}
          {title}
        </h2>
        {right}
      </div>
      {children}
    </motion.section>
  );
}
