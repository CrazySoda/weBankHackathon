import type { LucideIcon } from "lucide-react";
import { ArrowRight, Check } from "lucide-react";

interface GuidedEmptyStateProps {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  steps: string[];
  footnote?: string;
}

export default function GuidedEmptyState({
  icon: Icon,
  eyebrow,
  title,
  description,
  actionLabel,
  onAction,
  steps,
  footnote,
}: GuidedEmptyStateProps) {
  return (
    <section className="feature-empty-state">
      <div className="feature-empty-copy">
        <span className="feature-empty-icon"><Icon size={22} /></span>
        <span className="feature-empty-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        <p>{description}</p>
        {actionLabel && onAction && <button className="empty-state-button" onClick={onAction}>{actionLabel}<ArrowRight size={16}/></button>}
        {footnote && <small>{footnote}</small>}
      </div>
      <div className="feature-empty-steps" aria-label="What happens next">
        <span className="feature-steps-label">What happens next</span>
        {steps.map((step, index) => <div className="feature-empty-step" key={step}>
          <span>{index + 1}</span><strong>{step}</strong>{index < steps.length - 1 && <Check size={13} aria-hidden="true"/>}
        </div>)}
      </div>
    </section>
  );
}
