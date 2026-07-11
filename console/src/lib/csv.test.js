import { describe, expect, test } from "vitest";
import { parseFeedUpload, toPaymentsCsv } from "./csv.js";

describe("parseFeedUpload", () => {
  test("plain payments CSV -> payments kind", () => {
    const { kind, rows } = parseFeedUpload("payment_id,payee,amount\nP-1,Acme LLC,100\nP-2,Beta Co,50", "csv");
    expect(kind).toBe("payments");
    expect(rows).toEqual([
      { payment_id: "P-1", payee: "Acme LLC", amount: 100 },
      { payment_id: "P-2", payee: "Beta Co", amount: 50 },
    ]);
  });

  test("raw USAspending award CSV -> mapped (real columns, quoted fields, zero-amount skipped)", () => {
    const csv = [
      "recipient_name,contract_award_unique_key,current_total_value_of_award,award_description",
      '"LOCKHEED MARTIN CORP",CONT_AWD_ABC,15000000.50,"services, misc"',
      '"BOOZ ALLEN HAMILTON INC",CONT_AWD_DEF,250000,"consulting, advisory"',
      '"ZERO CORP",CONT_AWD_ZZZ,0,"no amount, skip"',
    ].join("\n");
    const { kind, rows } = parseFeedUpload(csv, "csv");
    expect(kind).toBe("award");
    expect(rows).toHaveLength(2); // zero-amount row dropped
    expect(rows[0]).toEqual({ payment_id: "USASPEND-UP-CONT_AWD_ABC", payee: "LOCKHEED MARTIN CORP", amount: 15000000.5 });
    expect(rows[1].payee).toBe("BOOZ ALLEN HAMILTON INC");
  });

  test("assistance award columns are also recognized", () => {
    const csv = "recipient_name,assistance_award_unique_key,total_obligated_amount\nState University,ASST_1,90000";
    const { kind, rows } = parseFeedUpload(csv, "csv");
    expect(kind).toBe("award");
    expect(rows[0]).toEqual({ payment_id: "USASPEND-UP-ASST_1", payee: "State University", amount: 90000 });
  });

  test("unrecognized columns -> null kind + error", () => {
    const { kind, rows, errors } = parseFeedUpload("foo,bar\n1,2", "csv");
    expect(kind).toBeNull();
    expect(rows).toHaveLength(0);
    expect(errors[0]).toMatch(/unrecognized columns/);
  });

  test("toPaymentsCsv escapes commas and quotes", () => {
    const csv = toPaymentsCsv([{ payment_id: "P-1", payee: 'A, "B" Co', amount: 10 }]);
    expect(csv.split("\n")[0]).toBe("payment_id,payee,amount");
    expect(csv).toContain('"A, ""B"" Co"');
  });
});
