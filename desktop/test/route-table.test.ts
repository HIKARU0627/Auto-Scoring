import { describe, expect, it } from "vitest";

import { declaredRoutePatterns } from "../src/renderer/core/app-routes.js";
import { ROUTE_TABLE } from "../src/renderer/navigation/route-table.js";

describe("route table", () => {
  it("declares the same patterns as AppRoutes", () => {
    expect(ROUTE_TABLE.map((route) => route.pattern).sort()).toEqual(
      [...declaredRoutePatterns].sort(),
    );
  });
});
