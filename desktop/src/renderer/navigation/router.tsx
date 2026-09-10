import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type JSX,
  type ReactNode,
} from "react";

import { AppRoutes } from "../core/app-routes.js";

export interface RouteParams {
  readonly testId?: string;
  readonly submissionId?: string;
  readonly questionId?: string;
}

export interface MatchedRoute {
  readonly location: string;
  readonly pathname: string;
  readonly params: RouteParams;
}

interface RouterContextValue {
  readonly location: string;
  readonly pathname: string;
  readonly params: RouteParams;
  readonly canPop: boolean;
  readonly push: (path: string) => void;
  readonly replace: (path: string) => void;
  readonly pop: () => void;
}

const RouterContext = createContext<RouterContextValue | null>(null);

function splitLocation(location: string): { pathname: string; search: string } {
  const queryIndex = location.indexOf("?");
  if (queryIndex === -1) {
    return { pathname: location, search: "" };
  }
  return {
    pathname: location.slice(0, queryIndex),
    search: location.slice(queryIndex),
  };
}

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

export function matchRoutePattern(
  pattern: string,
  location: string,
): MatchedRoute | null {
  const { pathname, search } = splitLocation(location);
  const patternSegments = pattern
    .split("/")
    .filter((segment) => segment.length > 0);
  const pathSegments = pathname
    .split("/")
    .filter((segment) => segment.length > 0);

  if (pattern === AppRoutes.home) {
    if (pathname !== AppRoutes.home) {
      return null;
    }
    const questionId = readQuestionId(search);
    const params: RouteParams = questionId === undefined ? {} : { questionId };
    return { location, pathname, params };
  }

  if (patternSegments.length !== pathSegments.length) {
    return null;
  }

  const params: {
    testId?: string;
    submissionId?: string;
    questionId?: string;
  } = {};
  for (let index = 0; index < patternSegments.length; index += 1) {
    const patternSegment = patternSegments[index] ?? "";
    const pathSegment = pathSegments[index] ?? "";
    if (patternSegment.startsWith(":")) {
      const key = patternSegment.slice(1);
      if (key === "testId") {
        params.testId = decodeSegment(pathSegment);
      } else if (key === "submissionId") {
        params.submissionId = decodeSegment(pathSegment);
      }
      continue;
    }
    if (patternSegment !== pathSegment) {
      return null;
    }
  }

  const questionId = readQuestionId(search);
  if (questionId !== undefined) {
    params.questionId = questionId;
  }

  return { location, pathname, params };
}

function readQuestionId(search: string): string | undefined {
  if (search.length === 0) {
    return undefined;
  }
  const query = new URLSearchParams(search);
  const value = query.get(AppRoutes.pdfReviewQuestionParam);
  return value === null ? undefined : value;
}

export function RouterProvider({
  initialStack,
  children,
}: {
  initialStack: readonly string[];
  children: ReactNode;
}): JSX.Element {
  const [stack, setStack] = useState<string[]>(() => [...initialStack]);

  const location = stack[stack.length - 1] ?? AppRoutes.home;
  const canPop = stack.length > 1;

  const push = useCallback((path: string) => {
    setStack((current) => [...current, path]);
  }, []);

  const replace = useCallback((path: string) => {
    setStack((current) => {
      if (current.length === 0) {
        return [path];
      }
      const next = [...current];
      next[next.length - 1] = path;
      return next;
    });
  }, []);

  const pop = useCallback(() => {
    setStack((current) =>
      current.length > 1 ? current.slice(0, -1) : current,
    );
  }, []);

  const { pathname } = splitLocation(location);
  const matched = matchAnyRoute(location);
  const params = matched?.params ?? {};

  const value = useMemo<RouterContextValue>(
    () => ({
      location,
      pathname,
      params,
      canPop,
      push,
      replace,
      pop,
    }),
    [canPop, location, params, pathname, pop, push, replace],
  );

  return (
    <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
  );
}

export function useRouter(): RouterContextValue {
  const value = useContext(RouterContext);
  if (value === null) {
    throw new Error("useRouter must be used within RouterProvider");
  }
  return value;
}

export function matchAnyRoute(location: string): MatchedRoute | null {
  const patterns = [
    AppRoutes.home,
    AppRoutes.starting,
    AppRoutes.intake,
    AppRoutes.settings,
    AppRoutes.testList,
    AppRoutes.testSettingsPattern,
    AppRoutes.submissionQueuePattern,
    AppRoutes.submissionConfirmPattern,
    AppRoutes.pdfReviewPattern,
  ];
  for (const pattern of patterns) {
    const matched = matchRoutePattern(pattern, location);
    if (matched !== null) {
      return matched;
    }
  }
  return null;
}
