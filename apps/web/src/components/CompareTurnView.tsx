import { templateLabelForCompare } from "../chatPrefs/outgoing";
import type { EffectiveChatPrefs } from "../chatPrefs/types";
import type { CompareTurn } from "../types";
import { ProbePane } from "./ProbePane";

interface Props {
  turn: CompareTurn;
}

export function CompareTurnView({ turn }: Props) {
  return (
    <article className="turn compare-turn" aria-label="Сравнение двух ответов">
      <div className="compare-thread-grid">
        <ProbePane title="Без шаблона" slot={turn.baseline} accent="neutral" />
        <ProbePane
          title={turn.templateLabel}
          slot={turn.constrained}
          accent="steps"
          showChecks
          checkKind="template"
        />
      </div>
    </article>
  );
}

export function compareTemplateLabel(effective: EffectiveChatPrefs): string {
  return templateLabelForCompare(
    effective.responseTemplateId,
    effective.promptControls,
    effective.customRulesText,
  );
}
