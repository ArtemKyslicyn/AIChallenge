/**
 * Nation cabinet roles — practices from Wazir / Qurultai / Pentarchy /
 * Deliberation-in-Silico: specialized institutional seats, president synthesizes.
 */

export type CabinetRole = "president" | "parliament" | "defense" | "economy";

export type CabinetSeat = {
  role: CabinetRole;
  title: string;
  brief: string;
};

export type CabinetVoice = {
  role: CabinetRole;
  title: string;
  text: string;
};

const TITLES: Record<CabinetRole, string> = {
  president: "Президент",
  parliament: "Парламент",
  defense: "Минобороны",
  economy: "Минэкономики",
};

const LINE_KEYS: { role: CabinetRole; keys: string[] }[] = [
  { role: "president", keys: ["президент", "president"] },
  { role: "parliament", keys: ["парламент", "parliament", "сенат", "конгресс"] },
  { role: "defense", keys: ["оборона", "минобороны", "defense", "defence"] },
  { role: "economy", keys: ["экономика", "минэкономики", "economy", "finance"] },
];

/** Shared 4-seat executive stack (fictional blocs, real institutional shape). */
export function defaultCabinet(nationId: string): CabinetSeat[] {
  const flavor: Record<string, Partial<Record<CabinetRole, string>>> = {
    atlantic: {
      president: "Исполнительная власть блока; итоговое РЕШЕНИЕ.",
      parliament: "Мандат коалиции; одобряет/тормозит эскалацию.",
      defense: "Доктрина сдерживания и кибер-периметр.",
      economy: "Санкции, логистика, tech_lead atlantic.",
    },
    pacific: {
      president: "Консенсусный лидер консорциума; итоговое РЕШЕНИЕ.",
      parliament: "Совет корпораций-государств; торговый мандат.",
      defense: "Асимметричная оборона и сенсорные сети.",
      economy: "Промполитика и tech_lead pacific.",
    },
    neutral: {
      president: "Координатор лиги; итоговое РЕШЕНИЕ.",
      parliament: "Ассамблея нейтралов; голос за деэскалацию.",
      defense: "Оборонительный минимум и мониторинг.",
      economy: "Гуманитарные коридоры и стабильность рынков.",
    },
  };
  const f = flavor[nationId] || {};
  return (Object.keys(TITLES) as CabinetRole[]).map((role) => ({
    role,
    title: TITLES[role],
    brief: f[role] || `${TITLES[role]} страны.`,
  }));
}

export function cabinetTitle(role: CabinetRole): string {
  return TITLES[role];
}

/** Parse ПРЕЗИДЕНТ:/ПАРЛАМЕНТ:/… lines from model output. */
export function parseCabinetVoices(content: string): CabinetVoice[] {
  const raw = content || "";
  const voices: CabinetVoice[] = [];
  for (const { role, keys } of LINE_KEYS) {
    let text = "";
    for (const key of keys) {
      const re = new RegExp(`${key}\\s*[:：]\\s*(.+)`, "i");
      const m = raw.match(re);
      if (m?.[1]) {
        text = m[1].trim().split(/\n/)[0].slice(0, 220);
        break;
      }
    }
    if (text) voices.push({ role, title: TITLES[role], text });
  }
  return voices;
}

export function formatCabinetPromptBlock(seats: CabinetSeat[]): string {
  const lines = seats.map((s) => `- ${s.title}: ${s.brief}`).join("\n");
  return (
    "Кабинет страны (каждый голос — 1 предложение, затем президент сводит):\n" +
    lines +
    "\nФормат ответа:\n" +
    "ПРЕЗИДЕНТ: …\nПАРЛАМЕНТ: …\nОБОРОНА: …\nЭКОНОМИКА: …\n" +
    "РЕШЕНИЕ: <итог президента>\n"
  );
}
