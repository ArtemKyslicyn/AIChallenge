/** Tiny mapper test for battle → conflict-emulation live patch. */

import { describe, expect, it } from "vitest";

import { battleToConflictPatch } from "./conflictBridge";

describe("battleToConflictPatch", () => {
  it("maps strike means to STRIKE order and war arc", () => {
    const patch = battleToConflictPatch({
      round: 3,
      stability: 40,
      panic: 70,
      techLead: { atlantic: 60, pacific: 45, neutral: 30 },
      escalation: 3,
      means: "strike",
      meansActor: "atlantic",
      lastDelta: "panic +4",
      cabinet: [{ role: "president", title: "Президент", text: "Удар" }],
      cabinetNationId: "atlantic",
    });
    expect(patch.turn).toBe(3);
    expect(patch.escalation).toBe("launch_ready");
    expect(patch.lastOrders?.[0]?.actor).toBe("ATL");
    expect(patch.lastOrders?.[0]?.action).toBe("STRIKE");
    expect(patch.arcs?.some((a) => a.kind === "war")).toBe(true);
    expect(patch.warSupport?.ATL).toBeCloseTo(0.6);
    expect(patch.animate).toBe(true);
  });
});
